"""Planar odometry integration helpers."""

from dataclasses import dataclass
import math


def normalize_angle(angle: float) -> float:
    """Normalize an angle to [-pi, pi)."""

    return (angle + math.pi) % (2.0 * math.pi) - math.pi


@dataclass
class PlanarOdometry:
    """Integrate body-frame planar velocity into the odom frame."""

    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

    def update(self, vx: float, vy: float, wz: float, dt: float) -> None:
        if not 0.0 < dt <= 0.25:
            return
        heading_midpoint = self.yaw + 0.5 * wz * dt
        self.x += (
            vx * math.cos(heading_midpoint)
            - vy * math.sin(heading_midpoint)
        ) * dt
        self.y += (
            vx * math.sin(heading_midpoint)
            + vy * math.cos(heading_midpoint)
        ) * dt
        self.yaw = normalize_angle(self.yaw + wz * dt)
