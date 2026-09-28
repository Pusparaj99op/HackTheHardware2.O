"""Dead-reckoning pose for the car-mounted phone.

Heading: the phone's gyro (browser `devicemotion` rotationRate) projected onto
the gravity direction, so it works whether the phone lies flat or stands up in
landscape. Distance: a calibrated speed model (m/s per throttle %), set to zero
when optical flow says the camera is not actually moving (stuck / blocked).
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .models import Pose, wrap_angle

ImuSample = tuple[float, Sequence[float], Sequence[float]]  # (t_ms, (alpha, beta, gamma) deg/s, gravity xyz)
MAX_IMU_GAP_S = 0.5


@dataclass(frozen=True)
class OdometryParams:
    speed_per_pct: float = 0.012  # m/s per throttle %; calibrate with tools/calibrate_speed.py
    deadband_pct: float = 5
    heading_sign: float = 1.0  # flip to -1 if turning left makes the map arrow turn right
    flow_moving_threshold: float = 0.004
    use_flow: bool = True


def yaw_rate_from_imu(rotation_rate_deg: Sequence[float], gravity: Sequence[float]) -> float:
    """Counter-clockwise yaw rate (rad/s) about the world vertical.

    rotation_rate_deg = (alpha, beta, gamma) = rates about device (z, x, y).
    gravity = accelerationIncludingGravity (points "up" when the phone is still).
    """
    alpha, beta, gamma = rotation_rate_deg
    gx, gy, gz = gravity
    norm = math.sqrt(gx * gx + gy * gy + gz * gz)
    if norm < 1e-3:
        return 0.0
    rate = (beta * gx + gamma * gy + alpha * gz) / norm
    return math.radians(rate)


def integrate(pose: Pose, speed: float, yaw_rate: float, dt: float) -> Pose:
    mid_theta = pose.theta + yaw_rate * dt / 2
    return Pose(
        x=pose.x + speed * math.cos(mid_theta) * dt,
        y=pose.y + speed * math.sin(mid_theta) * dt,
        theta=wrap_angle(pose.theta + yaw_rate * dt),
    )


def speed_estimate(throttle: float, flow_magnitude: float | None, params: OdometryParams) -> float:
    if abs(throttle) < params.deadband_pct:
        return 0.0
    if params.use_flow and flow_magnitude is not None and flow_magnitude < params.flow_moving_threshold:
        return 0.0
    return throttle * params.speed_per_pct


class Odometry:
    def __init__(self, params: OdometryParams) -> None:
        self._params = params
        self._pose = Pose()
        self._last_imu_ms: float | None = None

    @property
    def pose(self) -> Pose:
        return self._pose

    def reset(self, pose: Pose | None = None) -> None:
        self._pose = pose or Pose()

    def add_imu(self, samples: Iterable[ImuSample]) -> None:
        for t_ms, rotation, gravity in samples:
            previous, self._last_imu_ms = self._last_imu_ms, t_ms
            if previous is None:
                continue
            dt = (t_ms - previous) / 1000
            if dt <= 0 or dt > MAX_IMU_GAP_S:
                continue
            yaw = self._params.heading_sign * yaw_rate_from_imu(rotation, gravity)
            self._pose = Pose(self._pose.x, self._pose.y, wrap_angle(self._pose.theta + yaw * dt))

    def update(self, throttle: float, flow_magnitude: float | None, dt: float) -> None:
        speed = speed_estimate(throttle, flow_magnitude, self._params)
        self._pose = integrate(self._pose, speed, 0.0, dt)
