"""Safety arbiter: every behaviour's command passes through here before the car.

Priority: kill > bumper > car link > stale video > obstacle > speed cap.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import STOP, DriveCommand, clamp


@dataclass(frozen=True)
class SafetyInputs:
    killed: bool
    bumper_mask: int
    car_link_ok: bool
    video_fresh: bool
    obstacle_close: bool
    speed_cap: float
    requires_video: bool


@dataclass(frozen=True)
class SafetyDecision:
    command: DriveCommand
    reason: str | None


def _capped(cmd: DriveCommand, cap: float) -> DriveCommand:
    return DriveCommand(throttle=clamp(cmd.throttle, -cap, cap), steer=clamp(cmd.steer, -100, 100))


def arbitrate(cmd: DriveCommand, inputs: SafetyInputs) -> SafetyDecision:
    if inputs.killed:
        return SafetyDecision(STOP, "killed")
    capped = _capped(cmd, inputs.speed_cap)
    if inputs.bumper_mask and capped.throttle > 0:
        return SafetyDecision(DriveCommand(0, capped.steer), "bumper")
    if not inputs.car_link_ok:
        return SafetyDecision(STOP, "car-link")
    if inputs.requires_video and not inputs.video_fresh:
        return SafetyDecision(STOP, "video-stale")
    if inputs.obstacle_close and capped.throttle > 0:
        return SafetyDecision(DriveCommand(0, capped.steer), "obstacle")
    return SafetyDecision(capped, None)
