import json
import math

import pytest

from visionpilot.models import Pose
from visionpilot.odometry import Odometry, OdometryParams, integrate, speed_estimate, yaw_rate_from_imu
from visionpilot.path_memory import (
    Track,
    downsample,
    list_tracks,
    load_track,
    sanitize_name,
    save_track,
    with_bump,
    with_pose,
)

# ---------------- odometry ----------------
OP = OdometryParams()


def test_yaw_rate_phone_flat_uses_alpha():
    assert yaw_rate_from_imu((90, 0, 0), (0, 0, 9.8)) == pytest.approx(math.pi / 2)


def test_yaw_rate_phone_upright_landscape_uses_beta():
    # gravity reaction along device x (landscape, upright): yaw is rotation about device x (beta)
    assert yaw_rate_from_imu((0, 30, 0), (9.8, 0, 0)) == pytest.approx(math.radians(30))


def test_yaw_rate_without_gravity_is_zero():
    assert yaw_rate_from_imu((90, 90, 90), (0, 0, 0)) == 0


def test_integrate_straight_and_turned():
    assert integrate(Pose(), 1.0, 0.0, 0.5) == pytest.approx(Pose(0.5, 0.0, 0.0))
    moved = integrate(Pose(0, 0, math.pi / 2), 1.0, 0.0, 1.0)
    assert moved.x == pytest.approx(0, abs=1e-9)
    assert moved.y == pytest.approx(1.0)


def test_speed_estimate_deadband_stuck_and_model():
    assert speed_estimate(3, None, OP) == 0
    assert speed_estimate(40, 0.0, OP) == 0  # commanded but camera sees no motion = stuck
    assert speed_estimate(40, None, OP) == pytest.approx(40 * OP.speed_per_pct)
    assert speed_estimate(-40, 0.05, OP) == pytest.approx(-40 * OP.speed_per_pct)


def test_odometry_integrates_imu_heading_and_translation():
    odo = Odometry(OP)
    samples = [(t * 100.0, (90.0, 0.0, 0.0), (0.0, 0.0, 9.8)) for t in range(11)]
    odo.add_imu(samples)
    assert odo.pose.theta == pytest.approx(math.pi / 2, rel=1e-3)
    odo.update(throttle=50, flow_magnitude=None, dt=1.0)
    assert odo.pose.y == pytest.approx(50 * OP.speed_per_pct, rel=1e-3)


def test_odometry_heading_sign_flip_and_gap_rejection():
    odo = Odometry(OdometryParams(heading_sign=-1.0))
    odo.add_imu([(0.0, (90.0, 0, 0), (0, 0, 9.8)), (100.0, (90.0, 0, 0), (0, 0, 9.8))])
    assert odo.pose.theta == pytest.approx(-math.radians(9))
    odo.add_imu([(5000.0, (90.0, 0, 0), (0, 0, 9.8))])  # 4.9 s gap: ignored
    assert odo.pose.theta == pytest.approx(-math.radians(9))


def test_odometry_reset():
    odo = Odometry(OP)
    odo.update(throttle=50, flow_magnitude=None, dt=1.0)
    odo.reset(Pose(1, 2, 3))
    assert odo.pose == Pose(1, 2, 3)


# ---------------- path memory ----------------
def empty_track():
    return Track(name="demo", created="2026-09-28T10:00:00Z")


def test_with_pose_adds_first_point_then_skips_tiny_moves():
    track = with_pose(empty_track(), Pose(0, 0, 0), t=0.0)
    assert len(track.points) == 1
    same = with_pose(track, Pose(0.01, 0, 0), t=0.1)
    assert same is track
    moved = with_pose(track, Pose(0.2, 0, 0), t=0.2)
    assert len(moved.points) == 2
    turned = with_pose(moved, Pose(0.2, 0, math.radians(30)), t=0.3)
    assert len(turned.points) == 3


def test_with_bump_records_position():
    assert with_bump(empty_track(), Pose(1.0, 2.0, 0)).bumps == ((1.0, 2.0),)


def test_sanitize_name_blocks_path_tricks():
    assert sanitize_name("../../etc/passwd") == "______etc_passwd"
    assert sanitize_name("") == "track"
    assert len(sanitize_name("x" * 100)) == 40


def test_save_load_roundtrip(tmp_path):
    track = with_bump(with_pose(with_pose(empty_track(), Pose(0, 0, 0), 0.0), Pose(1, 1, 1), 1.0), Pose(1, 1, 0))
    path = save_track(track, tmp_path)
    assert path.name == "demo.json"
    raw = json.loads(path.read_text())
    assert raw["points"][1] == [1, 1, 1, 1.0]
    assert load_track(tmp_path, "demo") == track
    assert list_tracks(tmp_path) == ["demo"]


def test_load_missing_and_corrupt(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_track(tmp_path, "nope")
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(ValueError):
        load_track(tmp_path, "bad")
    (tmp_path / "shape.json").write_text(json.dumps({"name": "shape", "points": [[1, 2]]}))
    with pytest.raises(ValueError):
        load_track(tmp_path, "shape")


def test_downsample_keeps_ends():
    points = tuple((float(i), 0.0) for i in range(1000))
    small = downsample(points, 50)
    assert len(small) <= 50
    assert small[0] == points[0]
    assert small[-1] == points[-1]
    assert downsample(points[:10], 50) == points[:10]
