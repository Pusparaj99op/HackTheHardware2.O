"""Find the car in hand-held mode via the ArUco marker taped on its roof.

Print the marker (tools/print_aruco.py) and stick it so the edge labelled
FRONT points to the car's nose: corners 0->1 are the marker's top edge.
"""
from __future__ import annotations

import math

import numpy as np

from ..models import MarkerPose


def pose_from_corners(corners: np.ndarray, width: int, height: int) -> MarkerPose:
    """corners: (4, 2) pixel coords in ArUco order (TL, TR, BR, BL of the printed marker)."""
    pts = np.asarray(corners, dtype=np.float64).reshape(4, 2)
    center = pts.mean(axis=0)
    top_mid = (pts[0] + pts[1]) / 2
    heading = math.atan2(top_mid[1] - center[1], top_mid[0] - center[0])
    edge = float(np.mean([np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]))
    return MarkerPose(x=center[0] / width, y=center[1] / height, heading=heading, size=edge / width)


class MarkerTracker:
    def __init__(self, marker_id: int = 0) -> None:
        import cv2  # heavy import kept out of the pure maths above

        self._cv2 = cv2
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self._detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        self._marker_id = marker_id

    def find(self, frame_bgr: np.ndarray) -> MarkerPose | None:
        gray = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return None
        for marker_corners, marker_id in zip(corners, ids.flatten()):
            if int(marker_id) == self._marker_id:
                h, w = gray.shape
                return pose_from_corners(marker_corners, w, h)
        return None
