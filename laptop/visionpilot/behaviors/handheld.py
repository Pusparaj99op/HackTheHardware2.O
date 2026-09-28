"""HANDHELD: the phone watches the scene from outside and guides the car.

The car is found by the ArUco marker on its roof (position + heading). The goal
is a tapped floor point or a tapped object. Other YOLO boxes are obstacles and
push the desired heading away (potential field with a sideways component so a
head-on obstacle is driven around instead of stalling in front of it).
All maths is in normalised image space; +angle = clockwise on screen = steer right.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..models import STOP, Detection, DriveCommand, MarkerPose, clamp, wrap_angle
from .base import BehaviorOutput, WorldState

Point = tuple[float, float]


@dataclass(frozen=True)
class HandheldParams:
    throttle: float = 28
    sharp_turn_throttle: float = 22
    sharp_turn_deg: float = 100
    steer_per_deg: float = 2.0
    arrive_radius: float = 0.06
    influence: float = 0.15
    repulse_gain: float = 0.05
    tangent_gain: float = 1.0
    marker_timeout_s: float = 0.5


def _unit(dx: float, dy: float) -> Point:
    n = math.hypot(dx, dy)
    return (0.0, 0.0) if n < 1e-9 else (dx / n, dy / n)


def _closest_point(box: Detection, p: Point) -> Point:
    return clamp(p[0], box.x1, box.x2), clamp(p[1], box.y1, box.y2)


def desired_heading(car: Point, goal: Point, obstacles: Sequence[Detection], params: HandheldParams) -> float:
    to_goal = _unit(goal[0] - car[0], goal[1] - car[1])
    vx, vy = to_goal
    for box in obstacles:
        cp = _closest_point(box, car)
        d = max(math.dist(cp, car), 0.01)
        if d >= params.influence:
            continue
        strength = params.repulse_gain * (1 / d - 1 / params.influence)
        away = _unit(car[0] - box.cx, car[1] - box.cy)
        # sideways part of "away", perpendicular to the goal direction
        along = away[0] * to_goal[0] + away[1] * to_goal[1]
        side = _unit(away[0] - along * to_goal[0], away[1] - along * to_goal[1])
        if side == (0.0, 0.0):
            side = (-to_goal[1], to_goal[0])
        vx += strength * (away[0] + params.tangent_gain * side[0])
        vy += strength * (away[1] + params.tangent_gain * side[1])
    return math.atan2(vy, vx)


def handheld_command(
    car: MarkerPose, goal: Point, obstacles: Sequence[Detection], params: HandheldParams
) -> tuple[DriveCommand, float]:
    distance = math.dist((car.x, car.y), goal)
    if distance < params.arrive_radius:
        return STOP, distance
    error = wrap_angle(desired_heading((car.x, car.y), goal, obstacles, params) - car.heading)
    error_deg = math.degrees(error)
    steer = clamp(params.steer_per_deg * error_deg, -100, 100)
    throttle = params.throttle if abs(error_deg) < params.sharp_turn_deg else params.sharp_turn_throttle
    return DriveCommand(throttle, steer), distance


def goal_point(world: WorldState) -> tuple[Point | None, Detection | None]:
    """Floor point to drive to, plus the goal detection (if the goal is an object)."""
    target = world.target
    if target.point is not None:
        return target.point, None
    goal_det = None
    if target.track_id is not None:
        goal_det = next((d for d in world.detections if d.track_id == target.track_id), None)
    elif target.label:
        same = [d for d in world.detections if d.label == target.label]
        goal_det = max(same, key=lambda d: d.area) if same else None
    if goal_det is None:
        return None, None
    return (goal_det.cx, goal_det.y2), goal_det  # bottom-centre = where it touches the floor


class HandheldBehavior:
    requires_video = True

    def __init__(self, params: HandheldParams) -> None:
        self._params = params
        self._last_marker_time = float("-inf")
        self._last_command = STOP

    def reset(self) -> None:
        self._last_marker_time = float("-inf")
        self._last_command = STOP

    def step(self, world: WorldState) -> BehaviorOutput:
        goal, goal_det = goal_point(world)
        if goal is None:
            return BehaviorOutput(STOP, "tap a spot or an object for the car to drive to")
        car = world.marker
        if car is None:
            if world.now - self._last_marker_time <= self._params.marker_timeout_s:
                return BehaviorOutput(self._last_command, "car marker hidden, coasting")
            self._last_command = STOP
            return BehaviorOutput(STOP, "car not visible - keep the roof marker in view")

        self._last_marker_time = world.now
        obstacles = [
            d
            for d in world.detections
            if d is not goal_det and not d.contains(car.x, car.y)  # never avoid the goal or the car itself
        ]
        command, distance = handheld_command(car, goal, obstacles, self._params)
        self._last_command = command
        status = "arrived!" if command == STOP else f"driving to goal, {distance:.2f} away"
        return BehaviorOutput(command, status, focus=goal_det)
