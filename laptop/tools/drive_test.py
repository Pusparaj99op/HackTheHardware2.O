"""M0 hardware test: drive the car from this terminal, no server needed.

Keys (latched, Windows console):
  W forward   S reverse   SPACE stop motor
  A left      D right     E centre steering
  K kill      C clear kill/bumper      Q quit

Run from laptop/:  .venv/Scripts/python tools/drive_test.py --speed 40
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visionpilot.protocol import (  # noqa: E402
    bumper_names,
    decode_telemetry,
    encode_clear,
    encode_drive,
    encode_kill,
)

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None

SEND_HZ = 20


def read_key() -> str | None:
    if msvcrt is None or not msvcrt.kbhit():
        return None
    return msvcrt.getwch().lower()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--car-ip", help="car IP; default = learned from its telemetry")
    p.add_argument("--cmd-port", type=int, default=4210)
    p.add_argument("--telem-port", type=int, default=4211)
    p.add_argument("--speed", type=int, default=40, help="throttle percent for W/S")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if msvcrt is None:
        sys.exit("drive_test.py needs a Windows console (msvcrt).")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.telem_port))
    sock.setblocking(False)
    car_ip = args.car_ip
    throttle, steer, seq = 0, 0, 0
    telem_text = "waiting for car telemetry..."
    print(__doc__)
    while True:
        key = read_key()
        extra: bytes | None = None
        if key == "q":
            break
        throttle = {"w": args.speed, "s": -args.speed, " ": 0}.get(key, throttle)
        steer = {"a": -100, "d": 100, "e": 0}.get(key, steer)
        if key == "k":
            extra, throttle = encode_kill(), 0
        elif key == "c":
            extra = encode_clear()

        try:
            while True:
                data, addr = sock.recvfrom(128)
                telem = decode_telemetry(data)
                if telem:
                    car_ip = car_ip or addr[0]
                    names = ",".join(bumper_names(telem.bumper_mask)) or "-"
                    telem_text = f"car {addr[0]} state={telem.state.name} bumpers={names} batt={telem.battery_mv}mV"
        except BlockingIOError:
            pass
        except ConnectionResetError:
            pass  # Windows reports ICMP port-unreachable as a reset on UDP

        if car_ip:
            seq += 1
            if extra:
                sock.sendto(extra, (car_ip, args.cmd_port))
            sock.sendto(encode_drive(seq, throttle, steer), (car_ip, args.cmd_port))
        sys.stdout.write(f"\rthrottle={throttle:4d} steer={steer:4d} | {telem_text}      ")
        sys.stdout.flush()
        time.sleep(1 / SEND_HZ)

    if car_ip:
        sock.sendto(encode_drive(seq + 1, 0, 0), (car_ip, args.cmd_port))
    print("\nbye")


if __name__ == "__main__":
    main()
