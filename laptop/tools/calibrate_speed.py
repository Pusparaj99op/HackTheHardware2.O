"""Measure how fast the car goes per throttle % (for odometry / path memory).

1. Put the car on the floor with ~3 m of free space ahead, mark its start.
2. Run (from laptop/):  .venv/Scripts/python tools/calibrate_speed.py --throttle 40 --seconds 2
3. Measure the distance travelled and type it in.
4. Start the server with the printed value, e.g.  set VP_SPEED_PER_PCT=0.0123
Do NOT run while the VisionPilot server is running (both use UDP port 4211).
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visionpilot.protocol import decode_telemetry, encode_clear, encode_drive  # noqa: E402

SEND_HZ = 20


def find_car(sock: socket.socket, timeout_s: float = 5.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(128)
        except (BlockingIOError, ConnectionResetError):
            time.sleep(0.05)
            continue
        if decode_telemetry(data):
            return addr[0]
    sys.exit("No telemetry from the car - is it powered and on the hotspot?")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--throttle", type=int, default=40)
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--cmd-port", type=int, default=4210)
    p.add_argument("--telem-port", type=int, default=4211)
    args = p.parse_args()
    if not 10 <= args.throttle <= 100 or not 0.5 <= args.seconds <= 5:
        sys.exit("throttle must be 10-100 and seconds 0.5-5")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.telem_port))
    sock.setblocking(False)
    car = find_car(sock)
    print(f"Car at {car}. Driving {args.throttle}% for {args.seconds}s in 3 seconds...")
    time.sleep(3)
    sock.sendto(encode_clear(), (car, args.cmd_port))
    seq, end = 0, time.monotonic() + args.seconds
    while time.monotonic() < end:
        seq += 1
        sock.sendto(encode_drive(seq, args.throttle, 0), (car, args.cmd_port))
        time.sleep(1 / SEND_HZ)
    sock.sendto(encode_drive(seq + 1, 0, 0), (car, args.cmd_port))

    metres = float(input("Distance travelled in metres (e.g. 1.35): "))
    speed_per_pct = metres / args.seconds / args.throttle
    print(f"\nset VP_SPEED_PER_PCT={speed_per_pct:.5f}   (speed {metres / args.seconds:.2f} m/s at {args.throttle}%)")


if __name__ == "__main__":
    main()
