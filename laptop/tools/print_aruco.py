"""Make the roof marker for hand-held mode: laptop/data/aruco_car_id0.png

Print it so the black square is about 12 cm wide, and tape it flat on the car
roof with the FRONT arrow pointing to the car's nose.

Run from laptop/:  .venv/Scripts/python tools/print_aruco.py
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MARKER_ID = 0
MARKER_PX = 600
MARGIN_PX = 120
OUT = Path(__file__).resolve().parents[1] / "data" / f"aruco_car_id{MARKER_ID}.png"


def main() -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, MARKER_ID, MARKER_PX)
    size = MARKER_PX + 2 * MARGIN_PX
    sheet = np.full((size, size), 255, np.uint8)
    sheet[MARGIN_PX : MARGIN_PX + MARKER_PX, MARGIN_PX : MARGIN_PX + MARKER_PX] = marker
    mid = size // 2
    cv2.arrowedLine(sheet, (mid, MARGIN_PX - 20), (mid, 25), 0, 6, tipLength=0.4)
    cv2.putText(sheet, "FRONT", (mid + 25, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3, cv2.LINE_AA)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT), sheet)
    print(f"Saved {OUT} - print the black square ~12 cm wide.")


if __name__ == "__main__":
    main()
