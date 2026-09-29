"""All tunables in one place. Override the common ones with VP_* environment variables."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from .behaviors.explore import ExploreParams
from .behaviors.follow import FollowParams
from .behaviors.handheld import HandheldParams
from .behaviors.obstacles import ObstacleParams
from .behaviors.replay import ReplayParams
from .odometry import OdometryParams
from .perception.free_space import FreeSpaceParams

LAPTOP_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class NetConfig:
    host: str = "0.0.0.0"
    port: int = 8443
    tls: bool = True
    cert_dir: Path = LAPTOP_DIR / "certs"
    cmd_port: int = 4210
    telem_port: int = 4211
    discovery_port: int = 4212
    car_ip: str | None = "192.168.4.1"  # ESP32 access point; VP_CAR_IP overrides


@dataclass(frozen=True)
class ControlConfig:
    hz: float = 20.0
    ui_hz: float = 10.0
    speed_cap: float = 40.0
    telemetry_timeout_s: float = 0.5
    video_timeout_s: float = 0.6
    manual_timeout_s: float = 0.35
    override_hold_s: float = 1.0  # joystick released -> vision resumes after this
    ping_period_s: float = 0.5  # while disengaged, ping the car to receive telemetry


@dataclass(frozen=True)
class VisionConfig:
    yolo_model: str = "yolo11n.pt"
    yolo_conf: float = 0.35
    yolo_imgsz: int = 640
    depth_model: str = "depth-anything/Depth-Anything-V2-Small-hf"
    depth_size: tuple[int, int] = (224, 392)  # (h, w), multiples of 14
    marker_id: int = 0
    jpeg_quality: int = 70
    model_dir: Path = LAPTOP_DIR / "models"


@dataclass(frozen=True)
class Settings:
    net: NetConfig = field(default_factory=NetConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    follow: FollowParams = field(default_factory=FollowParams)
    explore: ExploreParams = field(default_factory=ExploreParams)
    replay: ReplayParams = field(default_factory=ReplayParams)
    handheld: HandheldParams = field(default_factory=HandheldParams)
    obstacles: ObstacleParams = field(default_factory=ObstacleParams)
    odometry: OdometryParams = field(default_factory=OdometryParams)
    free_space: FreeSpaceParams = field(default_factory=FreeSpaceParams)
    tracks_dir: Path = LAPTOP_DIR / "data" / "tracks"


def _number(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    base = Settings()
    net = replace(
        base.net,
        car_ip=env.get("VP_CAR_IP") or base.net.car_ip,
        port=int(_number(env, "VP_PORT", base.net.port)),
        tls=env.get("VP_NO_TLS", "") not in ("1", "true", "yes"),
    )
    control = replace(base.control, speed_cap=_number(env, "VP_SPEED_CAP", base.control.speed_cap))
    vision = replace(base.vision, yolo_model=env.get("VP_YOLO_MODEL") or base.vision.yolo_model)
    odometry = replace(
        base.odometry,
        speed_per_pct=_number(env, "VP_SPEED_PER_PCT", base.odometry.speed_per_pct),
        heading_sign=_number(env, "VP_HEADING_SIGN", base.odometry.heading_sign),
    )
    follow = replace(base.follow, vfov_deg=_number(env, "VP_VFOV", base.follow.vfov_deg))
    return replace(base, net=net, control=control, vision=vision, odometry=odometry, follow=follow)
