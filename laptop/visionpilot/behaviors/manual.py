"""MANUAL: drive with the dashboard keyboard / joystick. Always available as fallback."""
from __future__ import annotations

from .base import BehaviorOutput, WorldState


class ManualBehavior:
    requires_video = False

    def reset(self) -> None:
        return None

    def step(self, world: WorldState) -> BehaviorOutput:
        return BehaviorOutput(command=world.manual, status="manual driving")
