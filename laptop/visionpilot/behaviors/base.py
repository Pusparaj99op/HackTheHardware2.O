"""Common types for driving behaviours (MANUAL / FOLLOW / EXPLORE / REPLAY / HANDHELD)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import STOP, Detection, DriveCommand, MarkerPose, Pose, Target


@dataclass(frozen=True)
class WorldState:
    """Everything a behaviour may look at for one control tick."""

    now: float
    detections: tuple[Detection, ...] = ()
    target: Target = field(default_factory=Target)
    openness: tuple[float, ...] | None = None
    marker: MarkerPose | None = None
    pose: Pose = field(default_factory=Pose)
    bumper_mask: int = 0
    obstacle_close: bool = False
    manual: DriveCommand = STOP


@dataclass(frozen=True)
class BehaviorOutput:
    command: DriveCommand
    status: str
    target: Target | None = None  # updated target for the control loop to adopt
    focus: Detection | None = None  # detection to highlight in the UI


class Behavior(Protocol):
    requires_video: bool

    def reset(self) -> None: ...

    def step(self, world: WorldState) -> BehaviorOutput: ...
