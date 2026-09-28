from dataclasses import replace

from visionpilot.models import DriveCommand
from visionpilot.safety import SafetyInputs, arbitrate

ALL_CLEAR = SafetyInputs(
    killed=False,
    bumper_mask=0,
    car_link_ok=True,
    video_fresh=True,
    obstacle_close=False,
    speed_cap=40,
    requires_video=True,
)
FORWARD_RIGHT = DriveCommand(throttle=30, steer=50)


def test_all_clear_passes_command_through():
    decision = arbitrate(FORWARD_RIGHT, ALL_CLEAR)
    assert decision.command == FORWARD_RIGHT
    assert decision.reason is None


def test_kill_beats_everything():
    inputs = replace(ALL_CLEAR, killed=True, bumper_mask=7, car_link_ok=False)
    decision = arbitrate(FORWARD_RIGHT, inputs)
    assert decision.command == DriveCommand(0, 0)
    assert decision.reason == "killed"


def test_bumper_blocks_forward_but_allows_reverse():
    inputs = replace(ALL_CLEAR, bumper_mask=2)
    assert arbitrate(FORWARD_RIGHT, inputs).command.throttle == 0
    assert arbitrate(FORWARD_RIGHT, inputs).reason == "bumper"
    reverse = DriveCommand(throttle=-30, steer=-40)
    assert arbitrate(reverse, inputs).command == reverse


def test_car_link_down_stops():
    decision = arbitrate(FORWARD_RIGHT, replace(ALL_CLEAR, car_link_ok=False))
    assert decision.command == DriveCommand(0, 0)
    assert decision.reason == "car-link"


def test_stale_video_stops_only_vision_modes():
    stale = replace(ALL_CLEAR, video_fresh=False)
    assert arbitrate(FORWARD_RIGHT, stale).reason == "video-stale"
    assert arbitrate(FORWARD_RIGHT, stale).command == DriveCommand(0, 0)
    manual = replace(stale, requires_video=False)
    assert arbitrate(FORWARD_RIGHT, manual).command == FORWARD_RIGHT


def test_obstacle_blocks_forward_only():
    inputs = replace(ALL_CLEAR, obstacle_close=True)
    decision = arbitrate(FORWARD_RIGHT, inputs)
    assert decision.command == DriveCommand(0, 50)
    assert decision.reason == "obstacle"
    reverse = DriveCommand(-20, 0)
    assert arbitrate(reverse, inputs).command == reverse


def test_speed_cap_limits_throttle_both_directions():
    fast = DriveCommand(throttle=90, steer=0)
    assert arbitrate(fast, ALL_CLEAR).command.throttle == 40
    assert arbitrate(DriveCommand(-90, 0), ALL_CLEAR).command.throttle == -40


def test_steer_clamped():
    assert arbitrate(DriveCommand(0, 180), ALL_CLEAR).command.steer == 100
