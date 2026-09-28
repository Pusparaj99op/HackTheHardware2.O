"""REPLAY: drive a recorded track again with pure-pursuit on the odometry pose.

Vision stays on: an obstacle on the path pauses the replay until it clears.
Put the car back at the track's start, facing the same way, before replaying.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..models import STOP, DriveCommand, Pose, clamp, wrap_angle
from .base import BehaviorOutput, WorldState

Point = tuple[float, float]


@dataclass(frozen=True)
class ReplayParams:
    lookahead_m: float = 0.4
    goal_tolerance_m: float = 0.25
    wheelbase_m: float = 0.2
    max_steer_deg: float = 30.0
    throttle: float = 30
    search_window: int = 40


@dataclass(frozen=True)
class PursuitResult:
    steer: float
    index: int
    done: bool
    lookahead: Point | None


def pure_pursuit(pose: Pose, path: Sequence[Point], start_index: int, params: ReplayParams) -> PursuitResult:
    if not path:
        return PursuitResult(0.0, 0, True, None)
    here = (pose.x, pose.y)
    start = min(max(start_index, 0), len(path) - 1)
    end = min(len(path), start + params.search_window)
    closest = min(range(start, end), key=lambda i: math.dist(path[i], here))
    goal = path[-1]
    if math.dist(goal, here) <= params.goal_tolerance_m and closest >= len(path) - 3:
        return PursuitResult(0.0, closest, True, goal)

    look = next((path[i] for i in range(closest, len(path)) if math.dist(path[i], here) >= params.lookahead_m), goal)
    alpha = wrap_angle(math.atan2(look[1] - pose.y, look[0] - pose.x) - pose.theta)
    distance = max(math.dist(look, here), 1e-3)
    wheel_angle = math.atan(params.wheelbase_m * 2 * math.sin(alpha) / distance)
    # alpha > 0 means the path is to the LEFT; our steer convention is + = right.
    steer = clamp(-math.degrees(wheel_angle) / params.max_steer_deg * 100, -100, 100)
    return PursuitResult(steer, closest, False, look)


class ReplayBehavior:
    requires_video = True

    def __init__(self, params: ReplayParams) -> None:
        self._params = params
        self._path: tuple[Point, ...] = ()
        self._index = 0

    @property
    def path(self) -> tuple[Point, ...]:
        return self._path

    def load(self, points: Sequence[Point]) -> None:
        self._path = tuple(points)
        self._index = 0

    def reset(self) -> None:
        self._index = 0

    def step(self, world: WorldState) -> BehaviorOutput:
        if not self._path:
            return BehaviorOutput(STOP, "load a saved track to replay")
        result = pure_pursuit(world.pose, self._path, self._index, self._params)
        self._index = result.index
        if result.done:
            return BehaviorOutput(STOP, "replay finished - arrived at end of track")
        if world.obstacle_close:
            return BehaviorOutput(DriveCommand(0, result.steer), "paused: obstacle ahead")
        progress = f"{result.index + 1}/{len(self._path)}"
        return BehaviorOutput(DriveCommand(self._params.throttle, result.steer), f"replaying track {progress}")
