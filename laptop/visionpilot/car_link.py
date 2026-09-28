"""Async UDP link to the ESP32 car: sends drive packets, receives telemetry.

The car's IP is learned from the source address of its telemetry packets
(the car sends telemetry to the hotspot gateway = this laptop), unless a fixed
IP is configured.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .models import DriveCommand
from .protocol import Telemetry, decode_telemetry, encode_clear, encode_drive, encode_kill

log = logging.getLogger(__name__)


class CarLink(asyncio.DatagramProtocol):
    def __init__(
        self,
        cmd_port: int,
        telem_port: int,
        car_ip: str | None = None,
        telemetry_timeout_s: float = 0.5,
        bind_host: str = "0.0.0.0",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cmd_port = cmd_port
        self._telem_port = telem_port
        self._fixed_ip = car_ip
        self._car_ip = car_ip
        self._timeout = telemetry_timeout_s
        self._bind_host = bind_host
        self._clock = clock
        self._transport: asyncio.DatagramTransport | None = None
        self._telemetry: Telemetry | None = None
        self._telemetry_time = float("-inf")
        self._seq = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(self._bind_host, self._telem_port))

    # ---- asyncio.DatagramProtocol ----
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        telemetry = decode_telemetry(data)
        if telemetry is None:
            return
        if self._fixed_ip is None and self._car_ip != addr[0]:
            log.info("Car found at %s", addr[0])
            self._car_ip = addr[0]
        self._telemetry = telemetry
        self._telemetry_time = self._clock()

    def error_received(self, exc: Exception) -> None:
        log.warning("UDP error: %s", exc)

    # ---- public API ----
    @property
    def car_ip(self) -> str | None:
        return self._car_ip

    @property
    def telemetry(self) -> Telemetry | None:
        return self._telemetry

    @property
    def local_port(self) -> int:
        if self._transport is None:
            return self._telem_port
        return self._transport.get_extra_info("sockname")[1]

    def link_ok(self) -> bool:
        return self._clock() - self._telemetry_time <= self._timeout

    def send_drive(self, cmd: DriveCommand) -> None:
        self._seq += 1
        self._send(encode_drive(self._seq, cmd.throttle, cmd.steer))

    def send_kill(self) -> None:
        self._send(encode_kill())

    def send_clear(self) -> None:
        self._send(encode_clear())

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def _send(self, data: bytes) -> None:
        if self._transport is None or self._car_ip is None:
            return
        self._transport.sendto(data, (self._car_ip, self._cmd_port))
