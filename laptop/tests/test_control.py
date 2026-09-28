import json
from dataclasses import replace

import pytest

from visionpilot.config import load_settings
from visionpilot.control import ControlLoop, Mode
from visionpilot.models import STOP, Detection, Perception, Target
from visionpilot.protocol import CarState, Telemetry


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeLink:
    def __init__(self):
        self.sent = []
        self.kills = 0
        self.clears = 0
        self.telemetry = Telemetry(seq=0, bumper_mask=0, battery_mv=7800, state=CarState.OK)
        self.ok = True
        self.car_ip = "192.168.137.50"

    def link_ok(self):
        return self.ok

    def send_drive(self, cmd):
        self.sent.append(cmd)

    def send_kill(self):
        self.kills += 1

    def send_clear(self):
        self.clears += 1


@pytest.fixture
def rig(tmp_path):
    clock, link = FakeClock(), FakeLink()
    loop = ControlLoop(load_settings({}), link, clock=clock, tracks_dir=tmp_path)
    return loop, link, clock


def seen(clock, detections=(), openness=None, marker=None, flow=None):
    return Perception(
        frame_time=clock.now,
        processed_time=clock.now,
        width=640,
        height=360,
        detections=tuple(detections),
        openness=openness,
        marker=marker,
        flow=flow,
    )


BOTTLE = Detection(track_id=5, label="bottle", conf=0.9, x1=0.45, y1=0.45, x2=0.55, y2=0.55)


def test_starts_killed_and_sends_stop(rig):
    loop, link, _ = rig
    loop.tick(0.05)
    assert link.sent[-1] == STOP
    snap = loop.snapshot()
    assert snap["killed"] is True
    assert snap["safety"] == "killed"


def test_arm_then_manual_drive_then_timeout(rig):
    loop, link, clock = rig
    loop.arm()
    assert link.clears == 1
    loop.set_manual(30, -20)
    loop.tick(0.05)
    assert link.sent[-1].throttle == 30
    assert link.sent[-1].steer == -20
    clock.now += 0.5
    loop.tick(0.05)
    assert link.sent[-1] == STOP


def test_kill_stops_and_latches_car(rig):
    loop, link, _ = rig
    loop.arm()
    loop.set_manual(30, 0)
    loop.kill()
    loop.tick(0.05)
    assert link.kills == 1
    assert link.sent[-1] == STOP


def test_follow_by_class_locks_track_id(rig):
    loop, link, clock = rig
    loop.arm()
    loop.set_mode(Mode.FOLLOW)
    loop.set_target_class("bottle")
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.tick(0.05)
    assert link.sent[-1].throttle > 0
    assert loop.target == Target(track_id=5, label="bottle")


def test_follow_with_stale_video_stops(rig):
    loop, link, clock = rig
    loop.arm()
    loop.set_mode(Mode.FOLLOW)
    loop.set_target_class("bottle")
    loop.on_perception(seen(clock, [BOTTLE]))
    clock.now += 2.0
    loop.tick(0.05)
    assert link.sent[-1] == STOP
    assert loop.snapshot()["safety"] == "video-stale"


def test_tap_selects_detection_in_follow(rig):
    loop, _, clock = rig
    loop.set_mode(Mode.FOLLOW)
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.tap(0.5, 0.5)
    assert loop.target == Target(track_id=5, label="bottle")


def test_tap_on_floor_in_handheld_sets_point(rig):
    loop, _, clock = rig
    loop.set_mode(Mode.HANDHELD)
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.tap(0.1, 0.9)
    assert loop.target == Target(point=(0.1, 0.9))


def test_explore_reverses_when_center_blocked(rig):
    loop, link, clock = rig
    loop.arm()
    loop.set_mode(Mode.EXPLORE)
    loop.on_perception(seen(clock, openness=(0.9, 0.9, 0.05, 0.2, 0.2)))
    loop.tick(0.05)
    assert link.sent[-1].throttle < 0


def test_driving_records_trail_and_bumps(rig):
    loop, link, clock = rig
    loop.arm()
    for _ in range(20):
        loop.set_manual(50, 0)
        loop.tick(0.1)
        clock.now += 0.1
    assert len(loop.snapshot()["trail"]) > 2
    link.telemetry = replace(link.telemetry, bumper_mask=2)
    loop.tick(0.1)
    assert len(loop.snapshot()["bumps"]) == 1


def test_save_and_load_replay(rig, tmp_path):
    loop, _, clock = rig
    loop.arm()
    for _ in range(20):
        loop.set_manual(50, 0)
        loop.tick(0.1)
        clock.now += 0.1
    path = loop.save_track("hall loop")
    assert path.name == "hall_loop.json"
    assert "hall_loop" in loop.snapshot()["tracks"]
    loop.load_replay("hall_loop")
    assert loop.mode is Mode.REPLAY
    assert loop.snapshot()["ghost"]
    assert loop.snapshot()["pose"] == pytest.approx([0.0, 0.0, 0.0])


def test_speed_cap_is_clamped(rig):
    loop, _, _ = rig
    loop.set_speed_cap(150)
    assert loop.snapshot()["speed_cap"] == 100
    loop.set_speed_cap(-5)
    assert loop.snapshot()["speed_cap"] == 0


def test_snapshot_is_json_serialisable(rig):
    loop, _, clock = rig
    loop.set_mode(Mode.FOLLOW)
    loop.on_perception(seen(clock, [BOTTLE], openness=(1, 1, 1, 1, 1), flow=0.01))
    loop.tick(0.05)
    json.dumps(loop.snapshot())
