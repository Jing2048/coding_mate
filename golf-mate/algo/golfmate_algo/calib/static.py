"""Static bias estimation helpers."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]


def rest_bias(gyro: ArrayLike, accel: ArrayLike | None = None, n: int = 50) -> ArrayF:
    """Estimate gyro bias from the first ``n`` quiet samples."""
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    n = min(n, gyro.shape[0])
    return gyro[:n].mean(axis=0)


def apply_gyro_bias(gyro: ArrayLike, bias: ArrayLike) -> ArrayF:
    return np.asarray(gyro, dtype=np.float64).reshape(-1, 3) - np.asarray(
        bias, dtype=np.float64
    ).reshape(3)
