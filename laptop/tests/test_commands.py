from unittest.mock import Mock

import pytest

from visionpilot.commands import handle_command
from visionpilot.control import ControlLoop, Mode


@pytest.fixture
def control():
    c = Mock(spec=ControlLoop)
    c.labels = ["bottle", "person"]
    return c


def test_engage_release_arm_and_kill(control):
    assert handle_command(control, {"type": "engage"}) is None
    assert handle_command(control, {"type": "arm"}) is None  # legacy alias
    assert handle_command(control, {"type": "release"}) is None
    assert handle_command(control, {"type": "kill"}) is None
    assert control.engage.call_count == 2
    control.release.assert_called_once()
    control.kill.assert_called_once()


def test_assist_mode_accepted(control):
    assert handle_command(control, {"type": "mode", "mode": "assist"}) is None
    control.set_mode.assert_called_once_with(Mode.ASSIST)


def test_mode(control):
    assert handle_command(control, {"type": "mode", "mode": "follow"}) is None
    control.set_mode.assert_called_once_with(Mode.FOLLOW)
    assert "mode" in handle_command(control, {"type": "mode", "mode": "fly"})
    assert control.set_mode.call_count == 1


def test_manual_validates_numbers(control):
    assert handle_command(control, {"type": "manual", "throttle": 30, "steer": -10}) is None
    control.set_manual.assert_called_once_with(30.0, -10.0)
    assert handle_command(control, {"type": "manual", "throttle": "fast", "steer": 0})
    assert handle_command(control, {"type": "manual", "throttle": float("nan"), "steer": 0})
    assert handle_command(control, {"type": "manual", "throttle": True, "steer": 0})
    assert control.set_manual.call_count == 1


def test_tap_range(control):
    assert handle_command(control, {"type": "tap", "x": 0.5, "y": 0.25}) is None
    control.tap.assert_called_once_with(0.5, 0.25)
    assert handle_command(control, {"type": "tap", "x": 1.5, "y": 0.2})


def test_target_class(control):
    assert handle_command(control, {"type": "target_class", "label": "bottle"}) is None
    control.set_target_class.assert_called_with("bottle")
    assert handle_command(control, {"type": "target_class", "label": None}) is None
    control.set_target_class.assert_called_with(None)
    assert handle_command(control, {"type": "target_class", "label": "unicorn"})


def test_speed_cap_and_simple_actions(control):
    assert handle_command(control, {"type": "speed_cap", "value": 55}) is None
    control.set_speed_cap.assert_called_once_with(55.0)
    for kind, method in [
        ("clear_target", "clear_target"),
        ("clear_bumper", "clear_bumper"),
        ("odom_reset", "reset_odometry"),
    ]:
        assert handle_command(control, {"type": kind}) is None
        getattr(control, method).assert_called_once()


def test_track_save_and_load(control):
    assert handle_command(control, {"type": "track_save", "name": "hall"}) is None
    control.save_track.assert_called_once_with("hall")
    assert handle_command(control, {"type": "track_save", "name": "x" * 100})
    control.load_replay.side_effect = FileNotFoundError("no saved track named 'nope'")
    assert "nope" in handle_command(control, {"type": "track_load", "name": "nope"})


def test_imu_samples(control):
    msg = {"type": "imu", "samples": [[10.0, [1, 2, 3], [0, 0, 9.8]], [20.0, [1, 2, 3], [0, 0, 9.8]]]}
    assert handle_command(control, msg) is None
    samples = control.on_imu.call_args.args[0]
    assert samples[0] == (10.0, (1.0, 2.0, 3.0), (0.0, 0.0, 9.8))
    assert handle_command(control, {"type": "imu", "samples": [[1, [1, 2], [0, 0, 1]]]})
    assert handle_command(control, {"type": "imu", "samples": [[1, [1, 2, 3], [0, 0, 1]]] * 500})


def test_unknown_and_malformed(control):
    assert handle_command(control, {"type": "self_destruct"})
    assert handle_command(control, ["not", "a", "dict"])
    assert handle_command(control, {"no_type": 1})
