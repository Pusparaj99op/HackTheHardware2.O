"""Recorded tracks: the car's past path, bump locations, save/load as JSON.

File format (data/tracks/<name>.json):
  {"name": "hall_loop", "created": "2026-09-28T13:45:10Z",
   "points": [[x_m, y_m, theta_rad, t_s], ...], "bumps": [[x_m, y_m], ...]}
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .models import Pose, wrap_angle

MAX_NAME_LEN = 40
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


@dataclass(frozen=True)
class TrackPoint:
    x: float
    y: float
    theta: float
    t: float


@dataclass(frozen=True)
class Track:
    name: str
    created: str
    points: tuple[TrackPoint, ...] = ()
    bumps: tuple[tuple[float, float], ...] = ()

    @property
    def xy(self) -> tuple[tuple[float, float], ...]:
        return tuple((p.x, p.y) for p in self.points)


def new_track(name: str) -> Track:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Track(name=sanitize_name(name), created=created)


def with_pose(track: Track, pose: Pose, t: float, min_dist: float = 0.05, min_turn: float = math.radians(8)) -> Track:
    """Append the pose if the car moved or turned enough; otherwise return the same track."""
    if track.points:
        last = track.points[-1]
        moved = math.dist((last.x, last.y), (pose.x, pose.y)) >= min_dist
        turned = abs(wrap_angle(pose.theta - last.theta)) >= min_turn
        if not (moved or turned):
            return track
    return replace(track, points=track.points + (TrackPoint(pose.x, pose.y, pose.theta, t),))


def with_bump(track: Track, pose: Pose) -> Track:
    return replace(track, bumps=track.bumps + ((pose.x, pose.y),))


def sanitize_name(name: str) -> str:
    return _UNSAFE.sub("_", name)[:MAX_NAME_LEN] or "track"


def save_track(track: Track, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sanitize_name(track.name)}.json"
    payload = {
        "name": track.name,
        "created": track.created,
        "points": [[p.x, p.y, p.theta, p.t] for p in track.points],
        "bumps": [list(b) for b in track.bumps],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def load_track(directory: Path, name: str) -> Track:
    path = directory / f"{sanitize_name(name)}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no saved track named {name!r}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        points = tuple(TrackPoint(*(float(v) for v in p)) for p in raw["points"])
        bumps = tuple((float(b[0]), float(b[1])) for b in raw.get("bumps", []))
        return Track(name=str(raw["name"]), created=str(raw.get("created", "")), points=points, bumps=bumps)
    except (json.JSONDecodeError, KeyError, TypeError, IndexError, ValueError) as exc:
        raise ValueError(f"track file {path.name} is corrupt: {exc}") from exc


def list_tracks(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def downsample(points: tuple, max_points: int) -> tuple:
    """Evenly thin a point sequence for the dashboard, always keeping both ends."""
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    return tuple(points[round(i * step)] for i in range(max_points))
