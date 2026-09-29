"""MANUAL: drive with the dashboard keyboard / joystick. Always available as fallback."""
from __future__ import annotations

from .base import BehaviorOutput, WorldState


class ManualBehavior:
    requires_video = False

    def reset(self) -> None:
        return None

    def step(self, world: WorldState) -> BehaviorOutput:
        return BehaviorOutput(command=world.manual, status="manual driving")


class AssistBehavior(ManualBehavior):
    """ASSIST: you drive with the joysticks, vision auto-brakes before obstacles.

    The braking itself is the safety arbiter's obstacle stop; this mode just
    requires live video so the car never drives 'blind' in assist.
    """

    requires_video = True

    def step(self, world: WorldState) -> BehaviorOutput:
        return BehaviorOutput(command=world.manual, status="assist: you drive, vision brakes")
