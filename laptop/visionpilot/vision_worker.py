"""Background GPU thread: phone JPEG -> YOLO + depth + marker + flow -> Perception.

Only the newest frame is processed (older ones are dropped) so latency never
builds up. Each model loads independently; if one fails the others still run
and MANUAL driving keeps working.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import cv2
import numpy as np

from .config import Settings
from .models import Perception
from .perception.free_space import column_openness
from .perception.overlay import OverlayInfo, draw_overlay

log = logging.getLogger(__name__)
ResultCallback = Callable[[Perception, bytes], None]
DEPTH_MODES = {"manual", "follow", "explore", "replay"}
FLOW_MODES = {"manual", "follow", "explore", "replay"}


class VisionWorker:
    def __init__(self, settings: Settings, on_result: ResultCallback) -> None:
        self._s = settings
        self._on_result = on_result
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._pending: tuple[bytes, float] | None = None
        self._mode = "manual"
        self._overlay = OverlayInfo()
        self._detector = self._depth = self._marker = self._flow = None
        self.status = "loading AI models..."
        self.labels: list[str] = []
        self.fps = 0.0
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def submit(self, jpeg: bytes, received_at: float) -> None:
        with self._lock:
            self._pending = (jpeg, received_at)
        self._wake.set()

    def configure(self, mode: str, overlay: OverlayInfo) -> None:
        self._mode, self._overlay = mode, overlay  # atomic reference swaps

    # ------------------------------------------------------------ thread
    def _load_models(self) -> None:
        v = self._s.vision
        problems = []
        try:
            from .perception.detector import Detector

            self._detector = Detector(v.yolo_model, v.model_dir, v.yolo_conf, v.yolo_imgsz)
            self.labels = self._detector.labels
        except Exception as exc:  # noqa: BLE001 - keep running without YOLO
            log.exception("YOLO failed to load")
            problems.append(f"YOLO: {exc}")
        try:
            from .perception.depth_model import DepthModel

            self._depth = DepthModel(v.depth_model, v.depth_size)
        except Exception as exc:  # noqa: BLE001 - keep running without depth
            log.exception("Depth model failed to load")
            problems.append(f"depth: {exc}")
        from .perception.aruco import MarkerTracker
        from .perception.flow import FlowMeter

        self._marker = MarkerTracker(v.marker_id)
        self._flow = FlowMeter()
        self.status = "ready" if not problems else "degraded - " + "; ".join(problems)

    def _run(self) -> None:
        self._load_models()
        while not self._stopping.is_set():
            if not self._wake.wait(timeout=0.5):
                continue
            self._wake.clear()
            with self._lock:
                job, self._pending = self._pending, None
            if job is None:
                continue
            started = time.monotonic()
            try:
                self._process(*job)
            except Exception:  # noqa: BLE001 - one bad frame must not kill the thread
                log.exception("vision frame failed")
            elapsed = max(time.monotonic() - started, 1e-3)
            self.fps = 0.8 * self.fps + 0.2 * (1 / elapsed)

    def _process(self, jpeg: bytes, received_at: float) -> None:
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        mode, overlay = self._mode, self._overlay
        height, width = frame.shape[:2]
        detections = self._detector.detect(frame) if self._detector else ()
        disparity = self._depth.estimate(frame) if (self._depth and mode in DEPTH_MODES) else None
        openness = column_openness(disparity, self._s.free_space) if disparity is not None else None
        marker = self._marker.find(frame) if (self._marker and mode == "handheld") else None
        flow = None
        if self._flow:
            if mode in FLOW_MODES:
                flow = self._flow.measure(frame)
            else:
                self._flow.reset()
        perception = Perception(
            frame_time=received_at,
            processed_time=time.monotonic(),
            width=width,
            height=height,
            detections=detections,
            openness=openness,
            marker=marker,
            flow=flow,
        )
        depth_vis = None
        if disparity is not None:
            from .perception.depth_model import depth_colormap

            depth_vis = depth_colormap(disparity, width // 4, height // 4)
        annotated = draw_overlay(frame, perception, overlay, depth_vis)
        ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, self._s.vision.jpeg_quality])
        self._on_result(perception, buffer.tobytes() if ok else jpeg)
