"""Apple Watch ingress contract (no Swift — specs + synthetic batches only).

Aligned with watchOS 10+ ``CMBatchedSensorManager`` (Series 8 / Ultra+):

* Accelerometer up to **800 Hz**
* Device Motion up to **200 Hz**
* Batches delivered ~1× per second during an active HealthKit workout
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, WristSide


@dataclass(frozen=True)
class WatchSpec:
    accel_hz: float = 800.0
    device_motion_hz: float = 200.0
    batch_period_s: float = 1.0
    requires_workout: bool = True
    device_id_prefix: str = "apple_watch"
    # Algo typically consumes Device Motion rate for AHRS; impact may use 800 Hz.
    algo_fs_hz: float = 200.0


def make_watch_batch_packet(
    *,
    duration_s: float = 1.0,
    fs_hz: float | None = None,
    handedness: Handedness = Handedness.RIGHT,
    wrist: WristSide = WristSide.LEAD,
    device_id: str = "apple_watch/sim",
    seed: int = 0,
) -> ImuPacket:
    """Synthetic Watch-like batch for unit tests (near-rest + small motion)."""
    spec = WatchSpec()
    fs = float(fs_hz if fs_hz is not None else spec.algo_fs_hz)
    n = max(2, int(round(duration_s * fs)))
    t = np.arange(n, dtype=np.float64) / fs
    rng = np.random.default_rng(seed)
    gyro = 0.02 * rng.normal(size=(n, 3))
    accel = np.zeros((n, 3), dtype=np.float64)
    accel[:, 2] = 9.80665
    accel += 0.05 * rng.normal(size=(n, 3))
    return ImuPacket(
        frame=SensorFrame(
            fs_hz=fs,
            wrist=wrist,
            handedness=handedness,
            device_id=device_id,
            is_canonical=False,
        ),
        t=t,
        gyro=gyro,
        accel=accel,
    )
