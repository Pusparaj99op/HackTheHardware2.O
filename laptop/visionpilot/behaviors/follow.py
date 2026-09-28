"""FOLLOW: lock onto a YOLO-tracked object (by class or by tap) and drive after it.

Distance is estimated from the bounding-box height and a per-class real-world
height (pinhole model), so no depth sensor is needed.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..models import STOP, Detection, DriveCommand, Target, clamp
from .base import BehaviorOutput, WorldState

DEFAULT_HEIGHTS: Mapping[str, float] = {
    "person": 1.7,
    "bottle": 0.25,
    "cup": 0.12,
    "chair": 0.9,
    "sports ball": 0.22,
    "teddy bear": 0.3,
    "backpack": 0.45,
    "dog": 0.5,
    "cat": 0.3,
    "suitcase": 0.6,
    "potted plant": 0.4,
    "cell phone": 0.15,
    "book": 0.22,
}


@dataclass(frozen=True)
class FollowParams:
    stop_distance_m: float = 0.8
    slow_zone_m: float = 1.5  # throttle ramps min->max over this distance past the stop point
    max_throttle: float = 45
    min_throttle: float = 22
    steer_gain: float = 120  # steer % per unit of horizontal offset (-1..1)
    lost_timeout_s: float = 0.7
    reacquire_radius: float = 0.25
    vfov_deg: float = 45.0
    default_height_m: float = 0.4
    ref_heights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_HEIGHTS))


def estimate_distance(det: Detection, params: FollowParams) -> float:
    focal = 0.5 / math.tan(math.radians(params.vfov_deg) / 2)  # in frame-height units
    real_height = params.ref_heights.get(det.label, params.default_height_m)
    return real_height * focal / max(det.height, 1e-3)


def follow_command(det: Detection, params: FollowParams) -> DriveCommand:
    offset = (det.cx - 0.5) * 2
    steer = clamp(params.steer_gain * offset, -100, 100)
    distance = estimate_distance(det, params)
    if distance <= params.stop_distance_m:
        return DriveCommand(throttle=0, steer=steer)
    ramp = clamp((distance - params.stop_distance_m) / params.slow_zone_m, 0, 1)
    throttle = params.min_throttle + (params.max_throttle - params.min_throttle) * ramp
    return DriveCommand(throttle=throttle, steer=steer)


def pick_by_tap(detections: Sequence[Detection], x: float, y: float) -> Detection | None:
    """The smallest box under the finger (so a bottle wins over the person holding it)."""
    hits = [d for d in detections if d.contains(x, y)]
    return min(hits, key=lambda d: d.area) if hits else None


def select_target(
    detections: Sequence[Detection],
    target: Target,
    last: Detection | None,
    params: FollowParams,
) -> Detection | None:
    if target.track_id is not None:
        exact = next((d for d in detections if d.track_id == target.track_id), None)
        if exact is not None:
            return exact
        if last is not None and target.label:
            near = [
                d
                for d in detections
                if d.label == target.label and math.dist((d.cx, d.cy), (last.cx, last.cy)) <= params.reacquire_radius
            ]
            if near:
                return min(near, key=lambda d: math.dist((d.cx, d.cy), (last.cx, last.cy)))
        return None
    if target.label:
        same = [d for d in detections if d.label == target.label]
        return max(same, key=lambda d: d.area) if same else None
    return None


class FollowBehavior:
    requires_video = True

    def __init__(self, params: FollowParams) -> None:
        self._params = params
        self._last: Detection | None = None
        self._last_seen = float("-inf")
        self._last_command = STOP

    def reset(self) -> None:
        self._last = None
        self._last_seen = float("-inf")
        self._last_command = STOP

    def step(self, world: WorldState) -> BehaviorOutput:
        if world.target.is_empty or (world.target.track_id is None and not world.target.label):
            return BehaviorOutput(STOP, "pick a target: tap it or choose a class")
        det = select_target(world.detections, world.target, self._last, self._params)
        if det is None:
            lost_for = world.now - self._last_seen
            if lost_for <= self._params.lost_timeout_s:
                return BehaviorOutput(self._last_command, f"target hidden {lost_for:.1f}s, coasting")
            self._last_command = STOP
            return BehaviorOutput(STOP, f"searching for {world.target.label or 'target'}...")

        self._last, self._last_seen = det, world.now
        self._last_command = follow_command(det, self._params)
        distance = estimate_distance(det, self._params)
        arrived = distance <= self._params.stop_distance_m
        status = f"{'arrived at' if arrived else 'following'} {det.label} #{det.track_id} ~{distance:.1f} m"
        new_target = Target(track_id=det.track_id, label=det.label)
        return BehaviorOutput(
            command=self._last_command,
            status=status,
            target=new_target if new_target != world.target else None,
            focus=det,
        )
