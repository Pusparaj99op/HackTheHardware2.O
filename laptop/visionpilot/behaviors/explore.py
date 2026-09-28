"""AUTO-EXPLORE: wander toward the most open direction seen by the depth model.

When everything ahead is blocked (or a bumper fires) the car reverses with the
steering turned AWAY from the open side: reversing with left lock swings the
nose right, so the car ends up facing the open space.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import STOP, DriveCommand
from .base import BehaviorOutput, WorldState


@dataclass(frozen=True)
class ExploreParams:
    cruise_throttle: float = 35
    slow_throttle: float = 25
    slow_below: float = 0.5  # best openness below this -> slow down
    blocked_below: float = 0.2  # best openness below this -> back up
    center_bias: float = 0.08  # prefer going straight when options are equal
    backup_s: float = 0.8
    backup_throttle: float = -35


def _column_steers(count: int) -> list[float]:
    if count == 1:
        return [0.0]
    return [-100 + 200 * i / (count - 1) for i in range(count)]


def choose_direction(openness: Sequence[float], params: ExploreParams) -> tuple[int, float]:
    """Return (column index, steer %) of the best column."""
    steers = _column_steers(len(openness))
    scores = [o + params.center_bias * (1 - abs(s) / 100) for o, s in zip(openness, steers)]
    best = max(range(len(scores)), key=lambda i: scores[i])
    return best, steers[best]


class ExploreBehavior:
    requires_video = True

    def __init__(self, params: ExploreParams) -> None:
        self._params = params
        self._backup_until = float("-inf")
        self._backup_steer = 0.0
        self._flip = 1

    def reset(self) -> None:
        self._backup_until = float("-inf")

    def _start_backup(self, now: float, openness: Sequence[float] | None) -> None:
        side = 0.0
        if openness:
            _, side = choose_direction(openness, self._params)
            if side == 0:
                half = len(openness) // 2
                side = 1.0 if sum(openness[half + 1 :]) >= sum(openness[:half]) else -1.0
        if side == 0:
            self._flip = -self._flip
            side = self._flip
        self._backup_steer = -100.0 if side > 0 else 100.0
        self._backup_until = now + self._params.backup_s

    def step(self, world: WorldState) -> BehaviorOutput:
        p = self._params
        if world.now < self._backup_until:
            return BehaviorOutput(DriveCommand(p.backup_throttle, self._backup_steer), "backing up")

        blocked = world.openness is not None and max(world.openness) < p.blocked_below
        if world.bumper_mask or world.obstacle_close or blocked:
            self._start_backup(world.now, world.openness)
            reason = "bumper hit" if world.bumper_mask else "path blocked"
            return BehaviorOutput(DriveCommand(p.backup_throttle, self._backup_steer), f"{reason}, backing up")

        if world.openness is None:
            return BehaviorOutput(STOP, "waiting for depth vision")

        index, steer = choose_direction(world.openness, p)
        throttle = p.cruise_throttle if world.openness[index] >= p.slow_below else p.slow_throttle
        return BehaviorOutput(DriveCommand(throttle, steer), f"exploring, heading to column {index + 1}")
