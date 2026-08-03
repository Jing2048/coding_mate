"""CROP-lite: per-swing residual bias optimization on rest windows.

Inspired by task-informed constrained redundant optimization (CROP) for golf
putting IMUs, reduced to a single wrist node: estimate constant residual
accel/gyro biases that best satisfy address/finish rest physics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import minimize

from golfmate_algo.ahrs.init import rest_detection
from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]
G_NORM = float(np.linalg.norm(so3.G_WORLD))


@dataclass
class CropLiteResult:
    gyro_corr: ArrayF
    accel_corr: ArrayF
    delta_gyro: ArrayF
    delta_accel: ArrayF
    rest_fraction: float
    cost: float
    success: bool


def _rest_mask(
    gyro: ArrayF,
    accel: ArrayF,
    fs: float,
    phases_address: int | None,
    phases_finish: int | None,
) -> NDArray[np.bool_]:
    mask = rest_detection(gyro, accel, fs)
    n = gyro.shape[0]
    # Prefer early address and late finish windows when available
    prefer = np.zeros(n, dtype=bool)
    if phases_address is not None:
        lo = max(0, phases_address - int(0.15 * fs))
        hi = min(n, phases_address + int(0.05 * fs) + 1)
        prefer[lo:hi] = True
    if phases_finish is not None:
        lo = max(0, phases_finish - int(0.05 * fs))
        hi = min(n, phases_finish + int(0.2 * fs) + 1)
        prefer[lo:hi] = True
    if prefer.any() and mask.any():
        both = mask & prefer
        if both.sum() >= max(5, int(0.02 * fs)):
            return both
    if mask.sum() >= max(5, int(0.02 * fs)):
        return mask
    # Fallback: first and last 5% of the record
    k = max(3, int(0.05 * n))
    out = np.zeros(n, dtype=bool)
    out[:k] = True
    out[-k:] = True
    return out


def crop_lite_correct(
    gyro: ArrayLike,
    accel: ArrayLike,
    fs: float,
    *,
    address_idx: int | None = None,
    finish_idx: int | None = None,
    bound_gyro_rad_s: float = 0.03,  # ~1.7 deg/s
    bound_accel_m_s2: float = 0.15,
    min_improvement: float = 0.05,
) -> CropLiteResult:
    """Estimate and remove constant residual biases using rest constraints."""
    g = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    a = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = g.shape[0]
    if n < 10:
        return CropLiteResult(
            gyro_corr=g.copy(),
            accel_corr=a.copy(),
            delta_gyro=np.zeros(3),
            delta_accel=np.zeros(3),
            rest_fraction=0.0,
            cost=float("nan"),
            success=False,
        )

    mask = _rest_mask(g, a, fs, address_idx, finish_idx)
    rest_frac = float(mask.mean())
    g_r, a_r = g[mask], a[mask]

    def cost(x: ArrayF) -> float:
        db_g, db_a = x[:3], x[3:]
        gc = g_r - db_g
        ac = a_r - db_a
        # Rest: |a| ≈ g, mean gyro ≈ 0, accel direction stable
        a_norm = np.linalg.norm(ac, axis=1)
        c_a = float(np.mean((a_norm - G_NORM) ** 2))
        c_w = float(np.mean(np.sum(gc**2, axis=1)))
        # Soft: mean specific force should align with a single gravity direction
        mean_a = ac.mean(axis=0)
        mean_n = float(np.linalg.norm(mean_a)) + 1e-12
        c_dir = float(np.mean(np.sum((ac - mean_a) ** 2, axis=1)))
        c_level = (mean_n - G_NORM) ** 2
        return c_a + 40.0 * c_w + 0.5 * c_dir + 2.0 * c_level

    x0 = np.zeros(6, dtype=np.float64)
    cost0 = float(cost(x0))
    # Skip optimization when rest gyro is already quiet and |a|≈g
    rest_w = float(np.mean(np.linalg.norm(g_r, axis=1)))
    rest_a_err = float(np.mean(np.abs(np.linalg.norm(a_r, axis=1) - G_NORM)))
    if rest_w < 0.04 and rest_a_err < 0.08:
        return CropLiteResult(
            gyro_corr=g.copy(),
            accel_corr=a.copy(),
            delta_gyro=np.zeros(3),
            delta_accel=np.zeros(3),
            rest_fraction=rest_frac,
            cost=cost0,
            success=True,
        )

    bounds = [(-bound_gyro_rad_s, bound_gyro_rad_s)] * 3 + [
        (-bound_accel_m_s2, bound_accel_m_s2)
    ] * 3
    res = minimize(cost, x0, method="L-BFGS-B", bounds=bounds)
    dg, da = res.x[:3], res.x[3:]
    improved = bool(res.success) and (cost0 - float(res.fun)) >= min_improvement
    if not improved:
        return CropLiteResult(
            gyro_corr=g.copy(),
            accel_corr=a.copy(),
            delta_gyro=np.zeros(3),
            delta_accel=np.zeros(3),
            rest_fraction=rest_frac,
            cost=cost0,
            success=False,
        )
    return CropLiteResult(
        gyro_corr=g - dg,
        accel_corr=a - da,
        delta_gyro=dg.astype(np.float64),
        delta_accel=da.astype(np.float64),
        rest_fraction=rest_frac,
        cost=float(res.fun),
        success=True,
    )
