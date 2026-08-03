"""Self-built glove-card / magnetic tag ingress contract.

Continuous 6-axis MEMS at a configurable ODR; mount extrinsic captures the
magnetic standoff relative to the anatomical wrist frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, WristSide


@dataclass(frozen=True)
class GloveCardSpec:
    odr_hz: float = 500.0
    accel_range_g: float = 16.0
    gyro_range_dps: float = 2000.0
    device_id_prefix: str = "glove_card"
    # Default standoff identity; production fills a calibrated quaternion.
    default_mount_extrinsic: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


def make_glove_packet(
    *,
    duration_s: float = 1.5,
    fs_hz: float | None = None,
    handedness: Handedness = Handedness.RIGHT,
    wrist: WristSide = WristSide.LEAD,
    mount_extrinsic: tuple[float, float, float, float] | None = None,
    device_id: str = "glove_card/sim",
    seed: int = 1,
) -> ImuPacket:
    """Synthetic continuous glove-card stream for unit tests."""
    spec = GloveCardSpec()
    fs = float(fs_hz if fs_hz is not None else spec.odr_hz)
    n = max(2, int(round(duration_s * fs)))
    t = np.arange(n, dtype=np.float64) / fs
    rng = np.random.default_rng(seed)
    gyro = 0.03 * rng.normal(size=(n, 3))
    accel = np.zeros((n, 3), dtype=np.float64)
    accel[:, 2] = 9.80665
    accel += 0.08 * rng.normal(size=(n, 3))
    return ImuPacket(
        frame=SensorFrame(
            fs_hz=fs,
            wrist=wrist,
            handedness=handedness,
            mount_extrinsic=mount_extrinsic or spec.default_mount_extrinsic,
            device_id=device_id,
            is_canonical=False,
        ),
        t=t,
        gyro=gyro,
        accel=accel,
    )
