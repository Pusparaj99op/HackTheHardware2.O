"""Draw what the AI sees onto the frame streamed to the dashboard."""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from ..models import Perception

GREEN = (80, 230, 120)
BLUE = (255, 170, 60)
RED = (60, 60, 240)
CYAN = (230, 220, 40)
MAGENTA = (230, 80, 230)
WHITE = (245, 245, 245)
FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass(frozen=True)
class OverlayInfo:
    mode: str = "manual"
    status: str = ""
    safety: str | None = None
    focus_id: int | None = None
    target_point: tuple[float, float] | None = None


def _label(img: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.45, 1)
    cv2.rectangle(img, (x, y - th - 6), (x + tw + 6, y), color, -1)
    cv2.putText(img, text, (x + 3, y - 4), FONT, 0.45, (20, 20, 20), 1, cv2.LINE_AA)


def _draw_detections(img: np.ndarray, p: Perception, focus_id: int | None) -> None:
    h, w = img.shape[:2]
    for d in p.detections:
        color = GREEN if (focus_id is not None and d.track_id == focus_id) else BLUE
        top_left, bottom_right = (int(d.x1 * w), int(d.y1 * h)), (int(d.x2 * w), int(d.y2 * h))
        cv2.rectangle(img, top_left, bottom_right, color, 3 if color == GREEN else 2)
        _label(img, f"#{d.track_id} {d.label} {d.conf:.0%}", top_left[0], max(top_left[1], 16), color)


def _draw_openness(img: np.ndarray, openness: tuple[float, ...]) -> None:
    h, w = img.shape[:2]
    seg = w // len(openness)
    for i, value in enumerate(openness):
        color = (0, int(255 * value), int(255 * (1 - value)))
        cv2.rectangle(img, (i * seg + 2, h - 14), ((i + 1) * seg - 2, h - 4), color, -1)


def _draw_marker(img: np.ndarray, p: Perception) -> None:
    if p.marker is None:
        return
    h, w = img.shape[:2]
    cx, cy = int(p.marker.x * w), int(p.marker.y * h)
    tip = (int(cx + 50 * math.cos(p.marker.heading)), int(cy + 50 * math.sin(p.marker.heading)))
    cv2.circle(img, (cx, cy), 10, CYAN, 2)
    cv2.arrowedLine(img, (cx, cy), tip, CYAN, 3, tipLength=0.3)
    _label(img, "CAR", cx + 12, cy - 12, CYAN)


def _draw_target_point(img: np.ndarray, point: tuple[float, float] | None) -> None:
    if point is None:
        return
    h, w = img.shape[:2]
    x, y = int(point[0] * w), int(point[1] * h)
    cv2.drawMarker(img, (x, y), MAGENTA, cv2.MARKER_CROSS, 28, 3)
    cv2.circle(img, (x, y), 16, MAGENTA, 2)


def draw_overlay(
    frame: np.ndarray, perception: Perception, info: OverlayInfo, depth_vis: np.ndarray | None = None
) -> np.ndarray:
    img = frame.copy()
    _draw_detections(img, perception, info.focus_id)
    if perception.openness:
        _draw_openness(img, perception.openness)
    _draw_marker(img, perception)
    _draw_target_point(img, info.target_point)
    if depth_vis is not None:
        dh, dw = depth_vis.shape[:2]
        img[6 : 6 + dh, img.shape[1] - dw - 6 : img.shape[1] - 6] = depth_vis
    header = f"{info.mode.upper()} | {info.status}"
    cv2.putText(img, header, (8, 22), FONT, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, header, (8, 22), FONT, 0.55, WHITE, 1, cv2.LINE_AA)
    if info.safety:
        cv2.putText(img, f"SAFETY: {info.safety}", (8, 46), FONT, 0.6, RED, 2, cv2.LINE_AA)
    return img
