"""Dynamic-range compression and dual-path IMU signal split.

WIT-KinNet-style signed-log compression reduces the influence of impact
transients on orientation filters, while phase/impact detectors keep the raw
accelerometer so the broadband strike signature is not destroyed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]


def signed_log_compress(x: ArrayLike, scale: float = 9.80665) -> ArrayF:
    """Element-wise signed logarithmic dynamic-range compression.

    ``y = sign(x) * log1p(|x| / scale) * scale`` maps large spikes toward a
    softer dynamic range while preserving sign and small-signal slope ≈ 1.
    """
    arr = np.asarray(x, dtype=np.float64)
    s = max(float(scale), 1e-9)
    return np.sign(arr) * np.log1p(np.abs(arr) / s) * s


def inverse_second_order_sta(
    x: ArrayLike,
    fs: float,
    *,
    f0_hz: float = 18.0,
    zeta: float = 0.35,
    gain: float = 0.05,
) -> ArrayF:
    """Approximate inverse of a lightly-damped mount resonance.

    The forward mount model adds ``gain * mode``; here we subtract a filtered
    estimate of that mode. Disabled when ``gain <= 0`` or ``f0_hz <= 0``.
    """
    arr = np.asarray(x, dtype=np.float64).reshape(-1, 3).copy()
    if gain <= 0.0 or f0_hz <= 0.0 or arr.shape[0] < 3:
        return arr
    dt = 1.0 / max(float(fs), 1e-6)
    w0 = 2.0 * np.pi * f0_hz
    p = np.zeros(3, dtype=np.float64)
    v = np.zeros(3, dtype=np.float64)
    mode = np.zeros_like(arr)
    drive = np.vstack([np.zeros((1, 3)), np.diff(arr, axis=0)]) / dt
    for i in range(arr.shape[0]):
        a = drive[i] - 2.0 * zeta * w0 * v - (w0**2) * p
        v = v + a * dt
        p = p + v * dt
        mode[i] = p
    scale = np.max(np.abs(arr)) / (np.max(np.abs(mode)) + 1e-9)
    return arr - gain * scale * mode


@dataclass(frozen=True)
class DualPathSignals:
    """Raw path for events; compressed (+ optional STA) path for AHRS tilt."""

    gyro: ArrayF
    accel_raw: ArrayF
    accel_ahrs: ArrayF
    gyro_sta: ArrayF
    meta: dict[str, float]


def split_dual_path(
    gyro: ArrayLike,
    accel: ArrayLike,
    fs: float,
    *,
    log_scale: float = 9.80665,
    apply_sta: bool = True,
    sta_f0_hz: float = 18.0,
    sta_zeta: float = 0.35,
    sta_gain: float = 0.05,
) -> DualPathSignals:
    """Build the dual-path IMU view used by the extreme pipeline."""
    g = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    a = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    g_sta = inverse_second_order_sta(
        g, fs, f0_hz=sta_f0_hz, zeta=sta_zeta, gain=sta_gain if apply_sta else 0.0
    )
    a_sta = inverse_second_order_sta(
        a, fs, f0_hz=sta_f0_hz, zeta=sta_zeta, gain=sta_gain if apply_sta else 0.0
    )
    a_ahrs = signed_log_compress(a_sta, scale=log_scale)
    return DualPathSignals(
        gyro=g_sta,
        accel_raw=a,
        accel_ahrs=a_ahrs,
        gyro_sta=g_sta,
        meta={
            "log_scale": float(log_scale),
            "sta_applied": float(apply_sta),
            "sta_f0_hz": float(sta_f0_hz),
            "sta_gain": float(sta_gain if apply_sta else 0.0),
        },
    )
