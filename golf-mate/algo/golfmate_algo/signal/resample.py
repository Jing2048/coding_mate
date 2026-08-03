"""Resample irregular IMU streams to a fixed grid."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.types import ImuPacket, SensorFrame


def resample_packet(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    fs_hz: float,
    frame: SensorFrame | None = None,
) -> ImuPacket:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    if t.shape[0] < 2:
        raise ValueError("need >= 2 samples")
    t0, t1 = float(t[0]), float(t[-1])
    n = int(np.floor((t1 - t0) * fs_hz)) + 1
    tg = t0 + np.arange(n, dtype=np.float64) / fs_hz
    g = np.column_stack([np.interp(tg, t, gyro[:, i]) for i in range(3)])
    a = np.column_stack([np.interp(tg, t, accel[:, i]) for i in range(3)])
    if frame is None:
        frame = SensorFrame(fs_hz=fs_hz)
    else:
        frame = SensorFrame(
            fs_hz=fs_hz,
            wrist=frame.wrist,
            handedness=frame.handedness,
            mount_extrinsic=frame.mount_extrinsic,
            device_id=frame.device_id,
            is_canonical=frame.is_canonical,
        )
    return ImuPacket(frame=frame, t=tg, gyro=g, accel=a)
