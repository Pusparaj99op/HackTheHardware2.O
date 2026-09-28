"""Turn a monocular relative-depth map into "how open is each direction".

Depth-Anything outputs relative disparity (bigger = closer) with an unknown
scale. We normalise by the 95th percentile of the whole frame, which for a
low forward-facing camera is the floor right in front of the bumper, a fixed
distance away. That makes values roughly comparable frame to frame.

Only a horizontal band around the horizon is scored: the floor there is far
away, so anything "near" in the band is something standing on the floor.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FreeSpaceParams:
    band: tuple[float, float] = (0.3, 0.6)  # rows (fraction of height) that are scored
    columns: int = 5
    ref_percentile: float = 95.0
    column_percentile: float = 90.0
    clear_near: float = 0.3  # normalised nearness at/below which a column is fully open
    block_near: float = 0.6  # at/above which it is fully blocked


def column_openness(disparity: np.ndarray, params: FreeSpaceParams) -> tuple[float, ...]:
    """Openness per column, left to right: 1.0 = clear, 0.0 = blocked."""
    reference = float(np.percentile(disparity, params.ref_percentile))
    if reference <= 1e-6:
        return (0.0,) * params.columns
    height = disparity.shape[0]
    top, bottom = int(height * params.band[0]), max(int(height * params.band[1]), int(height * params.band[0]) + 1)
    band = disparity[top:bottom] / reference
    span = params.block_near - params.clear_near
    result = []
    for column in np.array_split(band, params.columns, axis=1):
        nearness = float(np.percentile(column, params.column_percentile))
        result.append(float(np.clip(1 - (nearness - params.clear_near) / span, 0.0, 1.0)))
    return tuple(result)
