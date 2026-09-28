"""Text UDP protocol between the laptop and the ESP32 car.

Laptop -> car:  "D,<seq>,<throttle>,<steer>"   drive (ints, -100..100)
                "K"                            kill latch
                "C"                            clear kill + bumper lock
Car -> laptop:  "T,<seq>,<bumperMask>,<battery_mV>,<state>"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .models import clamp

SEQ_MODULO = 2**32
BUMPER_BITS = (("left", 1), ("center", 2), ("right", 4))


class CarState(IntEnum):
    OK = 0
    WATCHDOG = 1
    BUMPER_LOCK = 2
    KILLED = 3


@dataclass(frozen=True)
class Telemetry:
    seq: int
    bumper_mask: int
    battery_mv: int
    state: CarState


def encode_drive(seq: int, throttle: float, steer: float) -> bytes:
    t = round(clamp(throttle, -100, 100))
    s = round(clamp(steer, -100, 100))
    return f"D,{seq % SEQ_MODULO},{t},{s}".encode("ascii")


def encode_kill() -> bytes:
    return b"K"


def encode_clear() -> bytes:
    return b"C"


def decode_telemetry(data: bytes) -> Telemetry | None:
    """Parse a telemetry packet; returns None for anything malformed."""
    try:
        parts = data.decode("ascii").strip().split(",")
    except UnicodeDecodeError:
        return None
    if len(parts) != 5 or parts[0] != "T":
        return None
    try:
        seq, mask, battery, state = (int(p) for p in parts[1:])
        car_state = CarState(state)
    except ValueError:
        return None
    return Telemetry(seq=seq, bumper_mask=mask, battery_mv=battery, state=car_state)


def bumper_names(mask: int) -> tuple[str, ...]:
    return tuple(name for name, bit in BUMPER_BITS if mask & bit)
