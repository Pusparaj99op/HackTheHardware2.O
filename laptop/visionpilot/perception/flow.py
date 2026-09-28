"""Is the camera actually moving? Dense optical flow on a tiny grayscale frame."""
from __future__ import annotations

import cv2
import numpy as np

FLOW_SIZE = (160, 90)


class FlowMeter:
    def __init__(self) -> None:
        self._previous: np.ndarray | None = None

    def reset(self) -> None:
        self._previous = None

    def measure(self, frame_bgr: np.ndarray) -> float | None:
        """Median flow magnitude as a fraction of frame width per frame (None on first frame)."""
        gray = cv2.cvtColor(cv2.resize(frame_bgr, FLOW_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        previous, self._previous = self._previous, gray
        if previous is None:
            return None
        flow = cv2.calcOpticalFlowFarneback(previous, gray, None, 0.5, 2, 9, 2, 5, 1.1, 0)
        magnitude = np.linalg.norm(flow, axis=2)
        return float(np.median(magnitude)) / FLOW_SIZE[0]
