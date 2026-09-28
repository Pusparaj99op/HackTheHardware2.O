"""Fake ESP32 car for testing the laptop stack without hardware.

Mirrors the firmware's safety logic (watchdog, kill latch, bumper lock).
Keys (Windows console): 1/2/3 toggle left/centre/right bumper, Q quit.

Run from laptop/:  .venv/Scripts/python tools/fake_car.py
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None

WATCHDOG_S = 0.3
TELEM_PERIOD_S = 0.1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--laptop-ip", default="127.0.0.1")
    p.add_argument("--cmd-port", type=int, default=4210)
    p.add_argument("--telem-port", type=int, default=4211)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.cmd_port))
    sock.setblocking(False)
    seq, throttle, steer, bumpers = 0, 0, 0, 0
    killed, locked, reversed_since_bump = False, False, False
    last_drive, last_telem = 0.0, 0.0
    print(__doc__)
    while True:
        now = time.monotonic()
        if msvcrt and msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            if key == "q":
                break
            if key in "123":
                bumpers ^= 1 << (int(key) - 1)
        if bumpers and not locked:
            locked, reversed_since_bump = True, False
            throttle = min(throttle, 0)
        if locked and not bumpers and reversed_since_bump:
            locked = False
        try:
            while True:
                data, _ = sock.recvfrom(64)
                msg = data.decode("ascii", "replace")
                if msg == "K":
                    killed, throttle, steer = True, 0, 0
                elif msg == "C":
                    killed, locked = False, False
                elif msg.startswith("D,"):
                    _, s, t, st = msg.split(",")
                    seq, last_drive = int(s), now
                    throttle, steer = (0, 0) if killed else (int(t), int(st))
                    if locked and throttle > 0:
                        throttle = 0
                    if locked and throttle < 0:
                        reversed_since_bump = True
        except (BlockingIOError, ConnectionResetError, ValueError):
            pass
        watchdog = now - last_drive > WATCHDOG_S
        if watchdog:
            throttle, steer = 0, 0
        state = 3 if killed else 2 if locked else 1 if watchdog else 0
        if now - last_telem >= TELEM_PERIOD_S:
            last_telem = now
            packet = f"T,{seq},{bumpers},7800,{state}".encode("ascii")
            sock.sendto(packet, (args.laptop_ip, args.telem_port))
        sys.stdout.write(f"\rseq={seq:6d} thr={throttle:4d} steer={steer:4d} bumpers={bumpers:03b} state={state}   ")
        sys.stdout.flush()
        time.sleep(0.01)
    print("\nbye")


if __name__ == "__main__":
    main()
