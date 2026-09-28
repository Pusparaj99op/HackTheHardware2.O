"""Validate and apply JSON commands from the dashboard / phone WebSockets.

Everything from the network is untrusted: each field is type- and range-checked
before it reaches the control loop. Returns None on success or an error string.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from .control import ControlLoop, Mode

log = logging.getLogger(__name__)
MAX_IMU_SAMPLES = 200
MAX_TRACK_NAME = 60


class CommandError(ValueError):
    pass


def _num(msg: dict, key: str, low: float = -math.inf, high: float = math.inf) -> float:
    value = msg.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CommandError(f"'{key}' must be a number")
    if not low <= value <= high:
        raise CommandError(f"'{key}' must be between {low} and {high}")
    return float(value)


def _vector(value: Any, length: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise CommandError(f"expected a list of {length} numbers")
    return tuple(_num({"v": v}, "v") for v in value)


def _imu(control: ControlLoop, msg: dict) -> None:
    samples = msg.get("samples")
    if not isinstance(samples, list) or len(samples) > MAX_IMU_SAMPLES:
        raise CommandError(f"'samples' must be a list of at most {MAX_IMU_SAMPLES}")
    parsed = []
    for sample in samples:
        if not isinstance(sample, list) or len(sample) != 3:
            raise CommandError("each IMU sample is [t_ms, [alpha, beta, gamma], [gx, gy, gz]]")
        parsed.append((_num({"t": sample[0]}, "t"), _vector(sample[1], 3), _vector(sample[2], 3)))
    control.on_imu(parsed)


def _mode(control: ControlLoop, msg: dict) -> None:
    try:
        control.set_mode(Mode(msg.get("mode")))
    except ValueError as exc:
        raise CommandError(f"unknown mode {msg.get('mode')!r}") from exc


def _target_class(control: ControlLoop, msg: dict) -> None:
    label = msg.get("label")
    if label is not None and (not isinstance(label, str) or (control.labels and label not in control.labels)):
        raise CommandError(f"unknown class {label!r}")
    control.set_target_class(label or None)


def _name(msg: dict) -> str:
    name = msg.get("name")
    if not isinstance(name, str) or not 0 < len(name) <= MAX_TRACK_NAME:
        raise CommandError(f"'name' must be 1-{MAX_TRACK_NAME} characters")
    return name


def _track_load(control: ControlLoop, msg: dict) -> None:
    try:
        control.load_replay(_name(msg))
    except (FileNotFoundError, ValueError) as exc:
        raise CommandError(str(exc)) from exc


HANDLERS: dict[str, Callable[[ControlLoop, dict], None]] = {
    "arm": lambda c, m: c.arm(),
    "kill": lambda c, m: c.kill(),
    "mode": _mode,
    "manual": lambda c, m: c.set_manual(_num(m, "throttle", -100, 100), _num(m, "steer", -100, 100)),
    "tap": lambda c, m: c.tap(_num(m, "x", 0, 1), _num(m, "y", 0, 1)),
    "target_class": _target_class,
    "clear_target": lambda c, m: c.clear_target(),
    "speed_cap": lambda c, m: c.set_speed_cap(_num(m, "value", 0, 100)),
    "clear_bumper": lambda c, m: c.clear_bumper(),
    "odom_reset": lambda c, m: c.reset_odometry(),
    "track_save": lambda c, m: c.save_track(_name(m)),
    "track_load": _track_load,
    "imu": _imu,
}


def handle_command(control: ControlLoop, msg: Any) -> str | None:
    if not isinstance(msg, dict):
        return "message must be a JSON object"
    handler = HANDLERS.get(msg.get("type"))  # type: ignore[arg-type]
    if handler is None:
        return f"unknown command type {msg.get('type')!r}"
    try:
        handler(control, msg)
    except CommandError as exc:
        return str(exc)
    except OSError as exc:
        log.exception("command %s failed", msg.get("type"))
        return f"{msg.get('type')} failed: {exc}"
    return None
