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
from .protocol import encode_discovery_reply, parse_discovery_request
from .vision_worker import VisionWorker

log = logging.getLogger(__name__)
WEB_DIR = LAPTOP_DIR / "web"
MAX_FRAME_BYTES = 1_000_000
SEND_ERRORS = (WebSocketDisconnect, RuntimeError, ConnectionError)


class Hub:
    """Connected screens.

    Dashboards (laptop page, controller app) get state JSON and, unless they opted out
    with ?frames=0, annotated video - each only once its previous frame was sent.
    Phones (/ws/phone) are camera sources; only the newest one is the active camera,
    so a Chrome page and the app camera never mix their frames.
    """

    def __init__(self) -> None:
        self._dash_busy: dict[WebSocket, bool] = {}  # socket -> busy sending a frame
        self._dash_frames: dict[WebSocket, bool] = {}  # socket -> wants video frames
        self._phones: list[WebSocket] = []  # connection order; last = active camera

    # ---- membership ----
    def add_dashboard(self, ws: WebSocket, frames: bool = True) -> None:
        self._dash_busy[ws] = False
        self._dash_frames[ws] = frames

    def remove_dashboard(self, ws: WebSocket) -> None:
        self._dash_busy.pop(ws, None)
        self._dash_frames.pop(ws, None)

    def add_phone(self, ws: WebSocket) -> None:
        self.remove_phone(ws)
        self._phones.append(ws)

    def remove_phone(self, ws: WebSocket) -> None:
        if ws in self._phones:
            self._phones.remove(ws)

    def is_active_camera(self, ws: WebSocket) -> bool:
        return bool(self._phones) and self._phones[-1] is ws

    @property
    def has_dashboards(self) -> bool:
        return bool(self._dash_busy)

    @property
    def has_phones(self) -> bool:
        return bool(self._phones)

    # ---- sending ----
    def push_frame(self, jpeg: bytes) -> None:
        for ws, busy in list(self._dash_busy.items()):
            if not busy and self._dash_frames.get(ws, False):
                self._dash_busy[ws] = True
                asyncio.create_task(self._send_frame(ws, jpeg))

    async def _send_frame(self, ws: WebSocket, jpeg: bytes) -> None:
        try:
            await ws.send_bytes(jpeg)
        except SEND_ERRORS:
            self.remove_dashboard(ws)
            return
        if ws in self._dash_busy:
            self._dash_busy[ws] = False

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload)
        for ws in [*self._dash_busy, *self._phones]:
            try:
                await ws.send_text(text)
            except SEND_ERRORS:
                self.remove_dashboard(ws)
                self.remove_phone(ws)


class DiscoveryResponder(asyncio.DatagramProtocol):
    """Answers the phone app's broadcast "VP?" so it can find this laptop's IP."""

    def __init__(self, port: int, tls: bool) -> None:
        self._reply = encode_discovery_reply(port, tls)
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport is not None and parse_discovery_request(data):
            self._transport.sendto(self._reply, addr)

    def error_received(self, exc: Exception) -> None:
        log.debug("discovery socket error: %s", exc)


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
            if self.control.engaged and not self.hub.has_dashboards:
                # the camera phone alone is not a controller: nobody can press KILL any more
                log.warning("No controller connected (app/dashboard) - releasing the car")
                self.control.release()
            self.control.vision_status = f"{self.worker.status} | {self.worker.fps:.0f} fps"
            self.control.labels = self.worker.labels
            snapshot = self.control.snapshot()
            snapshot["type"] = "state"
            snapshot["phone_connected"] = self.hub.has_phones
            await self.hub.broadcast(snapshot)

    async def apply(self, ws: WebSocket, text: str, camera_data_allowed: bool = True) -> None:
        try:
            message = json.loads(text)
        except ValueError:
            error = "invalid JSON"
        else:
            if not camera_data_allowed and isinstance(message, dict) and message.get("type") == "imu":
                return  # gyro of a phone that is not the active camera: ignore
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
        discovery, _ = await rt.loop.create_datagram_endpoint(
            lambda: DiscoveryResponder(settings.net.port, settings.net.tls),
            local_addr=("0.0.0.0", settings.net.discovery_port),
            allow_broadcast=True,
        )
        rt.worker.start()
        tasks = [asyncio.create_task(rt.control_task()), asyncio.create_task(rt.ui_task())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            rt.control.release()  # one STOP if we were driving; silent otherwise
            rt.worker.stop()
            discovery.close()
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
        # the controller app passes ?frames=0 when it shows its own camera preview
        rt.hub.add_dashboard(ws, frames=ws.query_params.get("frames") != "0")
        try:
            while True:
                await rt.apply(ws, await ws.receive_text())
        except WebSocketDisconnect:
            pass
        finally:
            rt.hub.remove_dashboard(ws)

    @app.websocket("/ws/phone")
    async def phone_socket(ws: WebSocket) -> None:
        await ws.accept()
        rt.hub.add_phone(ws)  # newest phone becomes the active camera
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                active = rt.hub.is_active_camera(ws)
                frame = message.get("bytes")
                if frame:
                    if active and len(frame) <= MAX_FRAME_BYTES:
                        rt.worker.submit(frame, time.monotonic())
                    continue
                if message.get("text"):
                    await rt.apply(ws, message["text"], camera_data_allowed=active)
        except WebSocketDisconnect:
            pass
        finally:
            rt.hub.remove_phone(ws)

    return app
