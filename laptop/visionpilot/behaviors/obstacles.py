"""Is something about to be hit? Used for the safety arbiter's obstacle stop (car-mounted camera)."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Detection


@dataclass(frozen=True)
class ObstacleParams:
    corridor: tuple[float, float] = (0.3, 0.7)  # horizontal band the car will drive through
    bottom_min: float = 0.85  # box must reach this low in the frame (= close to the bumper)
    min_height: float = 0.35  # and be this tall (normalised) to count as close
    depth_block: float = 0.15  # centre-column openness below this = blocked


def path_blocked(
    detections: Sequence[Detection],
    exclude_id: int | None,
    openness: Sequence[float] | None,
    params: ObstacleParams,
) -> bool:
    left, right = params.corridor
    for d in detections:
        if exclude_id is not None and d.track_id == exclude_id:
            continue
        overlaps = d.x2 >= left and d.x1 <= right
        if overlaps and d.y2 >= params.bottom_min and d.height >= params.min_height:
            return True
    if openness:
        return openness[len(openness) // 2] < params.depth_block
    return False
