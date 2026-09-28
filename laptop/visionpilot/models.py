"""Shared immutable value types passed between perception, behaviours and safety."""
from __future__ import annotations

import math
from dataclasses import dataclass


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_angle(angle: float) -> float:
    """Wrap an angle in radians to (-pi, pi]."""
    wrapped = math.atan2(math.sin(angle), math.cos(angle))
    return math.pi if wrapped == -math.pi else wrapped


@dataclass(frozen=True)
class DriveCommand:
    """throttle: -100..100 (+ = forward). steer: -100..100 (+ = right)."""

    throttle: float = 0.0
    steer: float = 0.0


STOP = DriveCommand()


@dataclass(frozen=True)
class Detection:
    """One tracked object. Box coordinates are normalised to 0..1 of the frame."""

    track_id: int | None
    label: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


@dataclass(frozen=True)
class MarkerPose:
    """The car seen from outside (hand-held mode), via its roof ArUco marker.

    x, y are normalised image coordinates. heading is in radians in image space:
    0 = pointing right, positive = clockwise on screen (image y grows downward).
    """

    x: float
    y: float
    heading: float
    size: float


@dataclass(frozen=True)
class Pose:
    """Odometry pose in metres / radians. theta is counter-clockwise positive."""

    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


@dataclass(frozen=True)
class Target:
    """What the car should go to. Exactly one field is normally set.

    point: a normalised image point (hand-held mode floor target).
    """

    track_id: int | None = None
    label: str | None = None
    point: tuple[float, float] | None = None

    @property
    def is_empty(self) -> bool:
        return self.track_id is None and self.label is None and self.point is None
