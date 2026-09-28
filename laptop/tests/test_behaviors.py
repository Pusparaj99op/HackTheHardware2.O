import math

import pytest

from visionpilot.behaviors.base import WorldState
from visionpilot.behaviors.explore import ExploreBehavior, ExploreParams, choose_direction
from visionpilot.behaviors.follow import (
    FollowBehavior,
    FollowParams,
    estimate_distance,
    follow_command,
    pick_by_tap,
    select_target,
)
from visionpilot.behaviors.handheld import HandheldBehavior, HandheldParams, desired_heading, handheld_command
from visionpilot.behaviors.manual import ManualBehavior
from visionpilot.behaviors.obstacles import ObstacleParams, path_blocked
from visionpilot.behaviors.replay import ReplayBehavior, ReplayParams, pure_pursuit
from visionpilot.models import STOP, Detection, DriveCommand, MarkerPose, Pose, Target


def det(track_id, label, x1, y1, x2, y2, conf=0.9):
    return Detection(track_id=track_id, label=label, conf=conf, x1=x1, y1=y1, x2=x2, y2=y2)


# ---------------- follow ----------------
FP = FollowParams()


def test_distance_from_box_height_uses_class_reference():
    person = det(1, "person", 0.4, 0.25, 0.6, 0.75)  # height 0.5
    focal = 0.5 / math.tan(math.radians(FP.vfov_deg) / 2)
    assert estimate_distance(person, FP) == pytest.approx(1.7 * focal / 0.5)


def test_unknown_class_uses_default_height():
    thing = det(1, "mystery", 0.4, 0.4, 0.6, 0.6)
    focal = 0.5 / math.tan(math.radians(FP.vfov_deg) / 2)
    assert estimate_distance(thing, FP) == pytest.approx(FP.default_height_m * focal / 0.2)


def test_far_centered_target_full_speed_straight():
    far = det(1, "person", 0.45, 0.45, 0.55, 0.55)  # tiny -> far
    cmd = follow_command(far, FP)
    assert cmd.steer == pytest.approx(0)
    assert cmd.throttle == pytest.approx(FP.max_throttle)


def test_target_on_right_steers_right():
    right = det(1, "person", 0.8, 0.45, 0.9, 0.55)
    assert follow_command(right, FP).steer > 0


def test_close_target_stops():
    close = det(1, "bottle", 0.2, 0.0, 0.8, 1.0)  # bottle filling the frame = ~0.3 m
    assert follow_command(close, FP).throttle == 0


def test_pick_by_tap_prefers_smallest_containing_box():
    big = det(1, "person", 0.1, 0.1, 0.9, 0.9)
    small = det(2, "bottle", 0.4, 0.4, 0.5, 0.6)
    assert pick_by_tap((big, small), 0.45, 0.5) == small
    assert pick_by_tap((big, small), 0.2, 0.2) == big
    assert pick_by_tap((small,), 0.95, 0.95) is None


def test_select_target_by_track_id():
    a = det(1, "bottle", 0.1, 0.1, 0.2, 0.3)
    b = det(2, "bottle", 0.6, 0.1, 0.8, 0.5)
    assert select_target((a, b), Target(track_id=1, label="bottle"), None, FP) == a


def test_select_target_reacquires_same_label_near_last_position():
    last = det(1, "bottle", 0.5, 0.4, 0.6, 0.6)
    new_id = det(9, "bottle", 0.52, 0.41, 0.62, 0.61)
    far = det(5, "bottle", 0.0, 0.0, 0.1, 0.1)
    assert select_target((far, new_id), Target(track_id=1, label="bottle"), last, FP) == new_id


def test_select_target_by_label_picks_largest():
    small = det(1, "cup", 0.1, 0.1, 0.15, 0.15)
    large = det(2, "cup", 0.5, 0.5, 0.7, 0.8)
    person = det(3, "person", 0.0, 0.0, 1.0, 1.0)
    assert select_target((small, large, person), Target(label="cup"), None, FP) == large


def test_follow_behavior_needs_a_target():
    out = FollowBehavior(FP).step(WorldState(now=1.0))
    assert out.command == STOP
    assert "target" in out.status


def test_follow_behavior_locks_id_then_coasts_then_stops_when_lost():
    behavior = FollowBehavior(FP)
    bottle = det(4, "bottle", 0.45, 0.45, 0.55, 0.55)
    first = behavior.step(WorldState(now=1.0, detections=(bottle,), target=Target(label="bottle")))
    assert first.target == Target(track_id=4, label="bottle")
    assert first.command.throttle > 0
    coasting = behavior.step(WorldState(now=1.3, target=Target(track_id=4, label="bottle")))
    assert coasting.command == first.command
    lost = behavior.step(WorldState(now=1.0 + FP.lost_timeout_s + 0.1, target=Target(track_id=4, label="bottle")))
    assert lost.command == STOP
    assert "searching" in lost.status


# ---------------- obstacles ----------------
OP = ObstacleParams()


def test_big_low_center_detection_blocks_path():
    chair = det(3, "chair", 0.35, 0.4, 0.65, 0.95)
    assert path_blocked((chair,), exclude_id=None, openness=None, params=OP)


def test_excluded_target_does_not_block():
    chair = det(3, "chair", 0.35, 0.4, 0.65, 0.95)
    assert not path_blocked((chair,), exclude_id=3, openness=None, params=OP)


def test_side_detection_does_not_block():
    side = det(3, "chair", 0.0, 0.4, 0.2, 0.95)
    assert not path_blocked((side,), exclude_id=None, openness=None, params=OP)


def test_depth_center_column_blocks():
    assert path_blocked((), exclude_id=None, openness=(1, 1, 0.05, 1, 1), params=OP)
    assert not path_blocked((), exclude_id=None, openness=(1, 1, 0.9, 1, 1), params=OP)


# ---------------- explore ----------------
EP = ExploreParams()


def test_choose_direction_prefers_most_open_column():
    index, steer = choose_direction((0.1, 0.2, 0.3, 0.9, 0.2), EP)
    assert index == 3
    assert steer == pytest.approx(50)


def test_choose_direction_center_bias_breaks_ties():
    index, steer = choose_direction((0.8, 0.8, 0.8, 0.8, 0.8), EP)
    assert index == 2
    assert steer == 0


def test_explore_waits_without_depth():
    out = ExploreBehavior(EP).step(WorldState(now=0.0))
    assert out.command == STOP


def test_explore_cruises_toward_open_space():
    out = ExploreBehavior(EP).step(WorldState(now=0.0, openness=(0.1, 0.1, 0.2, 0.9, 1.0)))
    assert out.command.throttle > 0
    assert out.command.steer == pytest.approx(100)


def test_explore_backs_up_after_bumper_then_resumes():
    behavior = ExploreBehavior(EP)
    open_right = (0.1, 0.1, 0.5, 0.9, 0.9)
    backing = behavior.step(WorldState(now=0.0, openness=open_right, bumper_mask=2))
    assert backing.command.throttle < 0
    assert backing.command.steer < 0  # reverse with left lock -> nose swings right (open side)
    still = behavior.step(WorldState(now=EP.backup_s / 2, openness=open_right))
    assert still.command.throttle < 0
    resumed = behavior.step(WorldState(now=EP.backup_s + 0.01, openness=open_right))
    assert resumed.command.throttle > 0


def test_explore_backs_up_when_everything_blocked():
    out = ExploreBehavior(EP).step(WorldState(now=0.0, openness=(0.05, 0.05, 0.05, 0.05, 0.05)))
    assert out.command.throttle < 0


# ---------------- replay ----------------
RP = ReplayParams()
STRAIGHT = tuple((i * 0.1, 0.0) for i in range(30))


def test_pure_pursuit_straight_path_goes_straight():
    result = pure_pursuit(Pose(0, 0, 0), STRAIGHT, 0, RP)
    assert result.steer == pytest.approx(0, abs=1e-6)
    assert not result.done


def test_pure_pursuit_path_to_left_steers_left():
    left_turn = tuple((0.1 * i, 0.02 * i * i) for i in range(20))
    assert pure_pursuit(Pose(0, 0, 0), left_turn, 0, RP).steer < 0


def test_pure_pursuit_done_at_goal():
    result = pure_pursuit(Pose(2.9, 0.0, 0.0), STRAIGHT, 25, RP)
    assert result.done


def test_replay_behavior_without_track_stops():
    out = ReplayBehavior(RP).step(WorldState(now=0.0))
    assert out.command == STOP


def test_replay_behavior_pauses_for_obstacle():
    behavior = ReplayBehavior(RP)
    behavior.load(STRAIGHT)
    out = behavior.step(WorldState(now=0.0, obstacle_close=True))
    assert out.command.throttle == 0
    assert "obstacle" in out.status
    moving = behavior.step(WorldState(now=0.1))
    assert moving.command.throttle > 0


# ---------------- handheld ----------------
HP = HandheldParams()


def test_goal_straight_ahead_no_steer():
    car = MarkerPose(x=0.2, y=0.5, heading=0.0, size=0.05)
    cmd, _ = handheld_command(car, (0.8, 0.5), (), HP)
    assert cmd.steer == pytest.approx(0, abs=1e-6)
    assert cmd.throttle > 0


def test_goal_below_on_screen_is_clockwise_so_steer_right():
    car = MarkerPose(x=0.2, y=0.5, heading=0.0, size=0.05)
    cmd, _ = handheld_command(car, (0.5, 0.8), (), HP)
    assert cmd.steer > 0


def test_arrived_stops():
    car = MarkerPose(x=0.5, y=0.5, heading=0.0, size=0.05)
    cmd, dist = handheld_command(car, (0.52, 0.5), (), HP)
    assert cmd == STOP
    assert dist < HP.arrive_radius


def test_obstacle_bends_desired_heading():
    blocker = det(1, "box", 0.45, 0.45, 0.55, 0.52)
    free = desired_heading((0.3, 0.5), (0.8, 0.5), (), HP)
    bent = desired_heading((0.38, 0.5), (0.8, 0.5), (blocker,), HP)
    assert free == pytest.approx(0)
    assert abs(bent) > 0.1


def test_handheld_behavior_without_marker_stops():
    out = HandheldBehavior(HP).step(WorldState(now=5.0, target=Target(point=(0.5, 0.5))))
    assert out.command == STOP
    assert "marker" in out.status


def test_handheld_behavior_drives_to_point_and_ignores_car_itself():
    car = MarkerPose(x=0.2, y=0.5, heading=0.0, size=0.05)
    car_box = det(7, "car", 0.15, 0.45, 0.25, 0.55)
    out = HandheldBehavior(HP).step(
        WorldState(now=1.0, marker=car, detections=(car_box,), target=Target(point=(0.8, 0.5)))
    )
    assert out.command.throttle > 0
    assert out.command.steer == pytest.approx(0, abs=1e-6)


# ---------------- manual ----------------
def test_manual_passes_through():
    cmd = DriveCommand(20, -30)
    behavior = ManualBehavior()
    assert behavior.step(WorldState(now=0.0, manual=cmd)).command == cmd
    assert not behavior.requires_video
