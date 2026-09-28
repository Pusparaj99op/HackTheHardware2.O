"""FastAPI server: phone + dashboard WebSockets, 20 Hz control task, UI broadcast.

Routes:
  /          admin dashboard (laptop)
  /phone     phone page (camera + gyro streamer, tap-to-track)
  /ws/phone  binary = JPEG frame, text = JSON command
  /ws/dash   text = JSON command; server pushes JSON state + binary annotated frames
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .car_link import CarLink
from .commands import handle_command
from .config import LAPTOP_DIR, Settings
from .control import ControlLoop
from .models import STOP, Perception
from .perception.overlay import OverlayInfo
from .vision_worker import VisionWorker

log = logging.getLogger(__name__)
WEB_DIR = LAPTOP_DIR / "web"
MAX_FRAME_BYTES = 1_000_000
SEND_ERRORS = (WebSocketDisconnect, RuntimeError, ConnectionError)


class Hub:
    """Connected browsers. A dashboard only gets a new frame once the previous send finished."""

    def __init__(self) -> None:
        self.dashboards: dict[WebSocket, bool] = {}  # socket -> busy sending a frame
        self.phones: set[WebSocket] = set()

    def push_frame(self, jpeg: bytes) -> None:
        for ws, busy in list(self.dashboards.items()):
            if not busy:
                self.dashboards[ws] = True
                asyncio.create_task(self._send_frame(ws, jpeg))

    async def _send_frame(self, ws: WebSocket, jpeg: bytes) -> None:
        try:
            await ws.send_bytes(jpeg)
        except SEND_ERRORS:
            self.dashboards.pop(ws, None)
            return
        if ws in self.dashboards:
            self.dashboards[ws] = False

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload)
        for ws in [*self.dashboards, *self.phones]:
            try:
                await ws.send_text(text)
            except SEND_ERRORS:
                self.dashboards.pop(ws, None)
                self.phones.discard(ws)


class Runtime:
    def __init__(self, settings: Settings) -> None:
        net = settings.net
        self.settings = settings
        self.link = CarLink(net.cmd_port, net.telem_port, net.car_ip, settings.control.telemetry_timeout_s)
        self.control = ControlLoop(settings, self.link)
        self.hub = Hub()
        self.worker = VisionWorker(settings, self._on_vision)
        self.loop: asyncio.AbstractEventLoop | None = None

    # vision thread -> event loop
    def _on_vision(self, perception: Perception, jpeg: bytes) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._deliver, perception, jpeg)

    def _deliver(self, perception: Perception, jpeg: bytes) -> None:
        self.control.on_perception(perception)
        self.hub.push_frame(jpeg)

    async def control_task(self) -> None:
        period = 1 / self.settings.control.hz
        last = time.monotonic()
        while True:
            await asyncio.sleep(period)
            now = time.monotonic()
            dt, last = min(now - last, 0.2), now
            try:
                self.control.tick(dt)
            except Exception:  # noqa: BLE001 - never leave the car driving on a crash
                log.exception("control tick failed; stopping car")
                self.link.send_drive(STOP)
            target = self.control.target
            self.worker.configure(
                self.control.mode.value,
                OverlayInfo(
                    mode=self.control.mode.value,
                    status=self.control.status,
                    safety=self.control.safety_reason,
                    focus_id=self.control.focus_id,
                    target_point=target.point,
                ),
            )

    async def ui_task(self) -> None:
        period = 1 / self.settings.control.ui_hz
        while True:
            await asyncio.sleep(period)
            if not self.hub.dashboards and not self.hub.phones and not self.control.killed:
                log.warning("All screens disconnected - killing car")
                self.control.kill()
            self.control.vision_status = f"{self.worker.status} | {self.worker.fps:.0f} fps"
            self.control.labels = self.worker.labels
            snapshot = self.control.snapshot()
            snapshot["type"] = "state"
            snapshot["phone_connected"] = bool(self.hub.phones)
            await self.hub.broadcast(snapshot)

    async def apply(self, ws: WebSocket, text: str) -> None:
        try:
            message = json.loads(text)
        except ValueError:
            error = "invalid JSON"
        else:
            error = handle_command(self.control, message)
        if error:
            with suppress(*SEND_ERRORS):
                await ws.send_text(json.dumps({"type": "error", "message": error}))


def create_app(settings: Settings) -> FastAPI:
    rt = Runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        rt.loop = asyncio.get_running_loop()
        await rt.link.start()
        rt.worker.start()
        tasks = [asyncio.create_task(rt.control_task()), asyncio.create_task(rt.ui_task())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            rt.link.send_drive(STOP)
            rt.worker.stop()
            rt.link.close()

    app = FastAPI(title="VisionPilot", lifespan=lifespan)
    app.state.runtime = rt
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    async def dashboard() -> FileResponse:
        return FileResponse(WEB_DIR / "dashboard.html")

    @app.get("/phone")
    async def phone_page() -> FileResponse:
        return FileResponse(WEB_DIR / "phone.html")

    @app.websocket("/ws/dash")
    async def dash_socket(ws: WebSocket) -> None:
        await ws.accept()
        rt.hub.dashboards[ws] = False
        try:
            while True:
                await rt.apply(ws, await ws.receive_text())
        except WebSocketDisconnect:
            pass
        finally:
            rt.hub.dashboards.pop(ws, None)

    @app.websocket("/ws/phone")
    async def phone_socket(ws: WebSocket) -> None:
        await ws.accept()
        rt.hub.phones.add(ws)
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                frame = message.get("bytes")
                if frame:
                    if len(frame) <= MAX_FRAME_BYTES:
                        rt.worker.submit(frame, time.monotonic())
                    continue
                if message.get("text"):
                    await rt.apply(ws, message["text"])
        except WebSocketDisconnect:
            pass
        finally:
            rt.hub.phones.discard(ws)

    return app
