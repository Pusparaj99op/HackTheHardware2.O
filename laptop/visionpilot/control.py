"""The 20 Hz brain loop: perception + telemetry -> behaviour -> safety -> car.

All user inputs (dashboard / phone) arrive as method calls; the loop owns the
mode, target, kill state, odometry and the live track.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Protocol

from .behaviors.base import BehaviorOutput, WorldState
from .behaviors.explore import ExploreBehavior
from .behaviors.follow import FollowBehavior, pick_by_tap
from .behaviors.handheld import HandheldBehavior
from .behaviors.manual import ManualBehavior
from .behaviors.obstacles import path_blocked
from .behaviors.replay import ReplayBehavior
from .config import Settings
from .models import STOP, DriveCommand, Perception, Pose, Target, clamp
from .odometry import ImuSample, Odometry
from .path_memory import (
    downsample,
    list_tracks,
    load_track,
    new_track,
    sanitize_name,
    save_track,
    with_bump,
    with_pose,
)
from .protocol import Telemetry, bumper_names
from .safety import SafetyDecision, SafetyInputs, arbitrate

log = logging.getLogger(__name__)
TRAIL_POINTS = 300


class Mode(str, Enum):
    MANUAL = "manual"
    FOLLOW = "follow"
    EXPLORE = "explore"
    REPLAY = "replay"
    HANDHELD = "handheld"


class CarLinkLike(Protocol):
    telemetry: Telemetry | None
    car_ip: str | None

    def link_ok(self) -> bool: ...
    def send_drive(self, cmd: DriveCommand) -> None: ...
    def send_kill(self) -> None: ...
    def send_clear(self) -> None: ...


def _r(value: float) -> float:
    return round(float(value), 3)


class ControlLoop:
    def __init__(
        self,
        settings: Settings,
        car_link: CarLinkLike,
        clock: Callable[[], float] = time.monotonic,
        tracks_dir: Path | None = None,
    ) -> None:
        self._s = settings
        self._link = car_link
        self._clock = clock
        self._tracks_dir = tracks_dir or settings.tracks_dir
        self._replay = ReplayBehavior(settings.replay)
        self._behaviors = {
            Mode.MANUAL: ManualBehavior(),
            Mode.FOLLOW: FollowBehavior(settings.follow),
            Mode.EXPLORE: ExploreBehavior(settings.explore),
            Mode.REPLAY: self._replay,
            Mode.HANDHELD: HandheldBehavior(settings.handheld),
        }
        self.mode = Mode.MANUAL
        self.killed = True  # start safe: the dashboard must ARM first
        self.target = Target()
        self.vision_status = "starting"
        self.labels: list[str] = []
        self._speed_cap = settings.control.speed_cap
        self._manual, self._manual_time = STOP, float("-inf")
        self._perception: Perception | None = None
        self._odometry = Odometry(settings.odometry)
        self._track = new_track("live")
        self._ghost: tuple[tuple[float, float], ...] = ()
        self._prev_bumpers = 0
        self._output = BehaviorOutput(STOP, "starting")
        self._decision = SafetyDecision(STOP, "killed")
        self._tracks = list_tracks(self._tracks_dir)
        self._notice = ""

    # ------------------------------------------------------------ read-only views
    @property
    def status(self) -> str:
        return self._output.status

    @property
    def safety_reason(self) -> str | None:
        return self._decision.reason

    @property
    def focus_id(self) -> int | None:
        return self._output.focus.track_id if self._output.focus else None

    # ------------------------------------------------------------ inputs
    def set_mode(self, mode: Mode) -> None:
        if mode is not self.mode:
            self._behaviors[mode].reset()
            self.mode = mode
            log.info("Mode -> %s", mode.value)

    def kill(self) -> None:
        self.killed = True
        self._link.send_kill()

    def arm(self) -> None:
        self.killed = False
        self._link.send_clear()

    def clear_bumper(self) -> None:
        if not self.killed:  # "C" also clears the car's kill latch, so never send it while killed
            self._link.send_clear()

    def set_manual(self, throttle: float, steer: float) -> None:
        self._manual = DriveCommand(clamp(throttle, -100, 100), clamp(steer, -100, 100))
        self._manual_time = self._clock()

    def set_speed_cap(self, value: float) -> None:
        self._speed_cap = clamp(value, 0, 100)

    def set_target_class(self, label: str | None) -> None:
        self.target = Target(label=label) if label else Target()

    def clear_target(self) -> None:
        self.target = Target()

    def tap(self, x: float, y: float) -> None:
        """Tap on the video (normalised coords): pick an object, or a floor spot in hand-held mode."""
        p = self._perception
        detections = p.detections if p else ()
        if self.mode is Mode.HANDHELD and p and p.marker:
            detections = tuple(d for d in detections if not d.contains(p.marker.x, p.marker.y))
        hit = pick_by_tap(detections, x, y)
        if hit is not None:
            self.target = Target(track_id=hit.track_id, label=hit.label)
        elif self.mode is Mode.HANDHELD:
            self.target = Target(point=(clamp(x, 0, 1), clamp(y, 0, 1)))

    def on_perception(self, perception: Perception) -> None:
        self._perception = perception

    def on_imu(self, samples: Iterable[ImuSample]) -> None:
        self._odometry.add_imu(samples)

    # ------------------------------------------------------------ tracks
    def reset_odometry(self) -> None:
        self._odometry.reset()
        self._track = new_track("live")
        self._ghost = ()

    def save_track(self, name: str) -> Path:
        path = save_track(replace(self._track, name=sanitize_name(name)), self._tracks_dir)
        self._tracks = list_tracks(self._tracks_dir)
        self._notice = f"saved track {path.stem}"
        return path

    def load_replay(self, name: str) -> None:
        track = load_track(self._tracks_dir, name)
        if not track.points:
            raise ValueError(f"track {name!r} has no points")
        self._replay.load(track.xy)
        start = track.points[0]
        self._odometry.reset(Pose(start.x, start.y, start.theta))
        self._track = new_track("live")
        self._ghost = track.xy
        self.set_mode(Mode.REPLAY)
        self._notice = f"loaded {track.name}: put the car at the start, facing the same way"

    # ------------------------------------------------------------ loop
    def tick(self, dt: float) -> None:
        now = self._clock()
        world, video_fresh, link_ok = self._world(now)
        behavior = self._behaviors[self.mode]
        self._output = behavior.step(world)
        if self._output.target is not None:
            self.target = self._output.target
        inputs = SafetyInputs(
            killed=self.killed,
            bumper_mask=world.bumper_mask,
            car_link_ok=link_ok,
            video_fresh=video_fresh,
            obstacle_close=world.obstacle_close,
            speed_cap=self._speed_cap,
            requires_video=behavior.requires_video,
        )
        self._decision = arbitrate(self._output.command, inputs)
        self._link.send_drive(self._decision.command)
        self._record(world, video_fresh, link_ok, dt)

    def _world(self, now: float) -> tuple[WorldState, bool, bool]:
        p = self._perception
        video_fresh = p is not None and now - p.frame_time <= self._s.control.video_timeout_s
        link_ok = self._link.link_ok()
        telem = self._link.telemetry
        bumpers = telem.bumper_mask if (telem and link_ok) else 0
        detections = p.detections if (p and video_fresh) else ()
        openness = p.openness if (p and video_fresh) else None
        manual_fresh = now - self._manual_time <= self._s.control.manual_timeout_s
        car_mounted_auto = self.mode in (Mode.FOLLOW, Mode.EXPLORE, Mode.REPLAY)
        exclude = self.target.track_id if self.mode is Mode.FOLLOW else None
        obstacle = car_mounted_auto and path_blocked(detections, exclude, openness, self._s.obstacles)
        world = WorldState(
            now=now,
            detections=detections,
            target=self.target,
            openness=openness,
            marker=p.marker if (p and video_fresh) else None,
            pose=self._odometry.pose,
            bumper_mask=bumpers,
            obstacle_close=obstacle,
            manual=self._manual if manual_fresh else STOP,
        )
        return world, video_fresh, link_ok

    def _record(self, world: WorldState, video_fresh: bool, link_ok: bool, dt: float) -> None:
        if self.mode is Mode.HANDHELD:
            return  # phone is not on the car: no odometry
        p = self._perception
        if not self._track.points:  # anchor every track at its true start pose
            self._track = with_pose(self._track, self._odometry.pose, world.now)
        throttle = self._decision.command.throttle if link_ok else 0.0
        self._odometry.update(throttle, p.flow if (p and video_fresh) else None, dt)
        pose = self._odometry.pose
        self._track = with_pose(self._track, pose, world.now)
        if world.bumper_mask and not self._prev_bumpers:
            self._track = with_bump(self._track, pose)
        self._prev_bumpers = world.bumper_mask

    # ------------------------------------------------------------ UI
    def snapshot(self) -> dict:
        telem = self._link.telemetry
        p = self._perception
        pose = self._odometry.pose
        cmd = self._decision.command
        focus = self._output.focus
        return {
            "mode": self.mode.value,
            "killed": self.killed,
            "status": self._output.status,
            "safety": self._decision.reason,
            "command": [round(cmd.throttle), round(cmd.steer)],
            "target": {
                "track_id": self.target.track_id,
                "label": self.target.label,
                "point": list(self.target.point) if self.target.point else None,
            },
            "focus": focus.track_id if focus else None,
            "speed_cap": self._speed_cap,
            "link": {
                "ok": self._link.link_ok(),
                "car_ip": self._link.car_ip,
                "state": telem.state.name if telem else None,
                "battery_mv": telem.battery_mv if telem else None,
                "bumpers": list(bumper_names(telem.bumper_mask)) if telem else [],
            },
            "pose": [_r(pose.x), _r(pose.y), _r(pose.theta)],
            "trail": [[_r(x), _r(y)] for x, y in downsample(self._track.xy, TRAIL_POINTS)],
            "bumps": [[_r(x), _r(y)] for x, y in self._track.bumps],
            "ghost": [[_r(x), _r(y)] for x, y in downsample(self._ghost, TRAIL_POINTS)],
            "detections": [
                {"id": d.track_id, "label": d.label, "conf": _r(d.conf), "box": [_r(d.x1), _r(d.y1), _r(d.x2), _r(d.y2)]}
                for d in (p.detections if p else ())
            ],
            "openness": [_r(o) for o in p.openness] if (p and p.openness) else None,
            "marker": {"x": _r(p.marker.x), "y": _r(p.marker.y), "heading": _r(p.marker.heading)}
            if (p and p.marker)
            else None,
            "vision": {
                "status": self.vision_status,
                "age_ms": round((self._clock() - p.frame_time) * 1000) if p else None,
                "flow": _r(p.flow) if (p and p.flow is not None) else None,
            },
            "tracks": self._tracks,
            "labels": self.labels,
            "notice": self._notice,
        }
