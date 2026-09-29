import json
from dataclasses import replace

import pytest

from visionpilot.config import load_settings
from visionpilot.control import ControlLoop, Mode
from visionpilot.models import STOP, Detection, DriveCommand, Perception, Target
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
        self.pings = 0
        self.telemetry = Telemetry(seq=0, bumper_mask=0, battery_mv=7800, state=CarState.OK)
        self.ok = True
        self.car_ip = "192.168.4.1"

    def link_ok(self):
        return self.ok

    def send_drive(self, cmd):
        self.sent.append(cmd)

    def send_kill(self):
        self.kills += 1

    def send_clear(self):
        self.clears += 1

    def send_ping(self):
        self.pings += 1


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


def run(loop, clock, seconds, dt=0.05):
    for _ in range(round(seconds / dt)):
        loop.tick(dt)
        clock.now += dt


BOTTLE = Detection(track_id=5, label="bottle", conf=0.9, x1=0.45, y1=0.45, x2=0.55, y2=0.55)
BOX_AHEAD = Detection(track_id=8, label="suitcase", conf=0.9, x1=0.35, y1=0.4, x2=0.65, y2=0.95)


# ---------------------------------------------------------------- engage / silence
def test_starts_disengaged_silent_but_pinging(rig):
    loop, link, clock = rig
    run(loop, clock, 1.0)
    assert link.sent == []  # never fights the phone app for the car
    assert link.pings >= 2
    snap = loop.snapshot()
    assert snap["engaged"] is False
    assert snap["safety"] == "standby"


def test_engage_then_manual_drive_then_timeout(rig):
    loop, link, clock = rig
    loop.engage()
    assert link.clears == 1
    loop.set_manual(30, -20)
    loop.tick(0.05)
    assert link.sent[-1] == DriveCommand(30, -20)
    clock.now += 0.5
    loop.tick(0.05)
    assert link.sent[-1] == STOP


def test_arm_is_an_alias_for_engage(rig):
    loop, link, _ = rig
    loop.arm()
    assert loop.snapshot()["engaged"] is True
    assert link.clears == 1


def test_release_sends_one_stop_then_goes_silent(rig):
    loop, link, clock = rig
    loop.engage()
    loop.set_manual(30, 0)
    loop.tick(0.05)
    loop.release()
    assert link.sent[-1] == STOP
    count = len(link.sent)
    run(loop, clock, 1.0)
    assert len(link.sent) == count
    assert link.kills == 0


def test_kill_latches_car_and_goes_silent(rig):
    loop, link, clock = rig
    loop.engage()
    loop.set_manual(30, 0)
    loop.kill()
    count = len(link.sent)
    run(loop, clock, 0.5)
    assert link.kills == 1
    assert len(link.sent) == count
    assert loop.snapshot()["engaged"] is False


# ---------------------------------------------------------------- follow
def engaged_follow(loop, clock):
    loop.engage()
    loop.set_mode(Mode.FOLLOW)
    loop.set_target_class("bottle")
    loop.on_perception(seen(clock, [BOTTLE]))


def test_follow_by_class_locks_track_id(rig):
    loop, link, clock = rig
    engaged_follow(loop, clock)
    loop.tick(0.05)
    assert link.sent[-1].throttle > 0
    assert loop.target == Target(track_id=5, label="bottle")


def test_follow_with_stale_video_stops(rig):
    loop, link, clock = rig
    engaged_follow(loop, clock)
    clock.now += 2.0
    loop.tick(0.05)
    assert link.sent[-1] == STOP
    assert loop.snapshot()["safety"] == "video-stale"


# ---------------------------------------------------------------- joystick override
def test_joystick_overrides_vision_then_vision_resumes_after_hold(rig):
    loop, link, clock = rig
    engaged_follow(loop, clock)
    loop.set_manual(-30, 60)
    loop.tick(0.05)
    assert link.sent[-1] == DriveCommand(-30, 60)
    assert "override" in loop.snapshot()["status"]

    clock.now += 0.5  # stick released: hold still before vision takes back
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.tick(0.05)
    assert link.sent[-1] == STOP
    assert "resum" in loop.snapshot()["status"]

    clock.now += 0.7  # > 1 s since the last stick input
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.tick(0.05)
    assert link.sent[-1].throttle > 0


# ---------------------------------------------------------------- assist (auto-brake)
def test_assist_passes_manual_when_path_clear(rig):
    loop, link, clock = rig
    loop.engage()
    loop.set_mode(Mode.ASSIST)
    loop.on_perception(seen(clock, [BOTTLE]))
    loop.set_manual(35, 10)
    loop.tick(0.05)
    assert link.sent[-1] == DriveCommand(35, 10)


def test_assist_brakes_forward_for_obstacle_but_allows_reverse(rig):
    loop, link, clock = rig
    loop.engage()
    loop.set_mode(Mode.ASSIST)
    loop.on_perception(seen(clock, [BOX_AHEAD]))
    loop.set_manual(35, 10)
    loop.tick(0.05)
    assert link.sent[-1].throttle == 0
    assert loop.snapshot()["safety"] == "obstacle"
    loop.set_manual(-30, 0)
    loop.tick(0.05)
    assert link.sent[-1].throttle == -30


def test_assist_needs_fresh_video(rig):
    loop, link, clock = rig
    loop.engage()
    loop.set_mode(Mode.ASSIST)
    loop.set_manual(35, 0)
    loop.tick(0.05)
    assert link.sent[-1] == STOP
    assert loop.snapshot()["safety"] == "video-stale"


# ---------------------------------------------------------------- targets
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
    loop.engage()
    loop.set_mode(Mode.EXPLORE)
    loop.on_perception(seen(clock, openness=(0.9, 0.9, 0.05, 0.2, 0.2)))
    loop.tick(0.05)
    assert link.sent[-1].throttle < 0


# ---------------------------------------------------------------- path memory
def drive_straight(loop, clock, seconds=2.0):
    for _ in range(round(seconds / 0.1)):
        loop.set_manual(50, 0)
        loop.tick(0.1)
        clock.now += 0.1


def test_driving_records_trail_and_bumps(rig):
    loop, link, clock = rig
    loop.engage()
    drive_straight(loop, clock)
    assert len(loop.snapshot()["trail"]) > 2
    link.telemetry = replace(link.telemetry, bumper_mask=2)
    loop.tick(0.1)
    assert len(loop.snapshot()["bumps"]) == 1


def test_save_and_load_replay(rig):
    loop, _, clock = rig
    loop.engage()
    drive_straight(loop, clock)
    path = loop.save_track("hall loop")
    assert path.name == "hall_loop.json"
    assert "hall_loop" in loop.snapshot()["tracks"]
    loop.load_replay("hall_loop")
    assert loop.mode is Mode.REPLAY
    assert loop.snapshot()["ghost"]
    assert loop.snapshot()["pose"] == pytest.approx([0.0, 0.0, 0.0])


def test_disengaged_car_does_not_move_the_odometry(rig):
    loop, _, clock = rig
    for _ in range(10):
        loop.set_manual(50, 0)
        loop.tick(0.1)
        clock.now += 0.1
    assert loop.snapshot()["pose"] == pytest.approx([0.0, 0.0, 0.0])


# ---------------------------------------------------------------- misc
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
    snap = loop.snapshot()
    json.dumps(snap)
    assert "assist" in snap["modes"]
