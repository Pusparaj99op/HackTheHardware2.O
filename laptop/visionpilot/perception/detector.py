"""YOLO11 object detection + ByteTrack IDs on the GPU (Ultralytics)."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..models import Detection

log = logging.getLogger(__name__)


class Detector:
    def __init__(self, model_name: str, model_dir: Path, conf: float, imgsz: int) -> None:
        import torch
        from ultralytics import YOLO

        cuda = torch.cuda.is_available()
        self._device = 0 if cuda else "cpu"
        model_dir.mkdir(parents=True, exist_ok=True)
        self._model = YOLO(str(model_dir / model_name))
        self._conf = conf
        self._imgsz = imgsz
        self.labels = sorted(self._model.names.values())
        log.info("YOLO %s loaded on %s", model_name, "cuda" if cuda else "cpu")

    def detect(self, frame_bgr: np.ndarray) -> tuple[Detection, ...]:
        height, width = frame_bgr.shape[:2]
        result = self._model.track(
            frame_bgr,
            persist=True,
            tracker="bytetrack.yaml",
            conf=self._conf,
            imgsz=self._imgsz,
            device=self._device,
            verbose=False,
        )[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return ()
        xyxy = boxes.xyxy.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else [None] * len(xyxy)
        names = self._model.names
        return tuple(
            Detection(
                track_id=None if tid is None else int(tid),
                label=names[int(c)],
                conf=float(cf),
                x1=float(b[0]) / width,
                y1=float(b[1]) / height,
                x2=float(b[2]) / width,
                y2=float(b[3]) / height,
            )
            for b, c, cf, tid in zip(xyxy, classes, confs, ids)
        )
