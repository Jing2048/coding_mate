"""Shared types for Golf Mate algorithm P0.

Quaternion convention throughout: [w, x, y, z] (scalar-first), float64.
IMU units: gyroscope rad/s, accelerometer m/s^2, timestamps seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from numpy.typing import NDArray


ArrayF = NDArray[np.floating[Any]]


class Handedness(str, Enum):
    RIGHT = "right"
    LEFT = "left"


class WristSide(str, Enum):
    LEAD = "lead"
    TRAIL = "trail"


@dataclass(frozen=True)
class SensorFrame:
    """Hardware-agnostic mounting / sampling contract.

    Watch and custom glove-card adapters map into this frame.
    ``mount_extrinsic`` rotates sensor body → wrist anatomical frame (identity if unknown).
    """

    fs_hz: float
    wrist: WristSide = WristSide.LEAD
    handedness: Handedness = Handedness.RIGHT
    mount_extrinsic: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    device_id: str = "unknown"


@dataclass(frozen=True)
class ImuSample:
    t: float
    gyro: tuple[float, float, float]
    accel: tuple[float, float, float]


@dataclass
class ImuPacket:
    """Fixed-rate IMU batch after resampling."""

    frame: SensorFrame
    t: ArrayF  # (N,)
    gyro: ArrayF  # (N, 3) rad/s
    accel: ArrayF  # (N, 3) m/s^2

    def __post_init__(self) -> None:
        self.t = np.asarray(self.t, dtype=np.float64).reshape(-1)
        self.gyro = np.asarray(self.gyro, dtype=np.float64).reshape(-1, 3)
        self.accel = np.asarray(self.accel, dtype=np.float64).reshape(-1, 3)
        n = self.t.shape[0]
        if self.gyro.shape[0] != n or self.accel.shape[0] != n:
            raise ValueError("t/gyro/accel length mismatch")


@dataclass
class SwingPhases:
    address_idx: int
    top_idx: int
    impact_idx: int
    finish_idx: int

    def as_dict(self) -> dict[str, int]:
        return {
            "address": self.address_idx,
            "top": self.top_idx,
            "impact": self.impact_idx,
            "finish": self.finish_idx,
        }

    def validate_order(self) -> None:
        if not (
            0 <= self.address_idx < self.top_idx < self.impact_idx < self.finish_idx
        ):
            raise ValueError(f"invalid phase order: {self.as_dict()}")


@dataclass
class WristFeatures:
    tempo_s: float
    backswing_s: float
    downswing_s: float
    rhythm: float  # backswing / downswing
    peak_omega_rad_s: float
    peak_omega_idx: int
    peak_omega_to_impact_s: float
    hand_speed_peak_m_s: float
    plane_angle_deg: float
    closure_rate_rad_s: float
    extras: dict[str, float] = field(default_factory=dict)


@dataclass
class DiagnosticFinding:
    code: str
    severity: str  # info | warn | critical
    message: str
    evidence: dict[str, float] = field(default_factory=dict)
    is_proxy: bool = True


@dataclass
class SwingReport:
    phases: SwingPhases
    features: WristFeatures
    findings: list[DiagnosticFinding]
    quats: ArrayF  # (N, 4)
    positions: ArrayF  # (N, 3)
    velocities: ArrayF  # (N, 3)
    gate_open: ArrayF  # (N,) accel-correction gate
    meta: dict[str, Any] = field(default_factory=dict)
