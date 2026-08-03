"""Assumption-breaking corruptions for zero-trust synthetic evaluation.

These deliberately violate the rigid-fixed-center model that the lever-arm
solver assumes. Ground-truth pose/position stay physical (from multibody);
only the *measured* IMU streams are corrupted so residual_rms / fallback
behaviour can be graded honestly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]


@dataclass(frozen=True)
class ViolationSpec:
    """Which physical assumptions to break."""

    center_translate_amp_m: float = 0.0  # slow sinusoid on world centre
    center_translate_hz: float = 1.5
    wrist_hinge_amp_rad: float = 0.0  # body-frame hinge jitter on accel/gyro
    wrist_hinge_hz: float = 8.0
    mount_slide_amp_m: float = 0.0  # soft mount slide along local y
    impact_nonlinear_g: float = 0.0  # extra broadband spike at impact
    seed: int = 0


def mild_violation(seed: int = 0) -> ViolationSpec:
    return ViolationSpec(
        center_translate_amp_m=0.04,
        wrist_hinge_amp_rad=0.08,
        mount_slide_amp_m=0.015,
        impact_nonlinear_g=2.5,
        seed=seed,
    )


def harsh_violation(seed: int = 0) -> ViolationSpec:
    return ViolationSpec(
        center_translate_amp_m=0.10,
        wrist_hinge_amp_rad=0.20,
        mount_slide_amp_m=0.04,
        impact_nonlinear_g=6.0,
        seed=seed,
    )


def apply_violations(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    *,
    quats_true: ArrayLike,
    positions_true: ArrayLike,
    impact_idx: int,
    spec: ViolationSpec,
) -> tuple[ArrayF, ArrayF, dict[str, float]]:
    """Return corrupted (gyro, accel) and a diagnostics dict.

    Position/orientation truth are *not* modified: the algorithm is graded
    against the physical swing, while measurements no longer match a rigid L.
    """
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    g = np.asarray(gyro, dtype=np.float64).reshape(-1, 3).copy()
    a = np.asarray(accel, dtype=np.float64).reshape(-1, 3).copy()
    quats = np.asarray(quats_true, dtype=np.float64).reshape(-1, 4)
    pos = np.asarray(positions_true, dtype=np.float64).reshape(-1, 3)
    n = t.shape[0]
    rng = np.random.default_rng(spec.seed)
    meta: dict[str, float] = {
        "center_translate_amp_m": spec.center_translate_amp_m,
        "wrist_hinge_amp_rad": spec.wrist_hinge_amp_rad,
        "mount_slide_amp_m": spec.mount_slide_amp_m,
        "impact_nonlinear_g": spec.impact_nonlinear_g,
    }

    # 1) Translating rotation centre → fictitious specific force in body frame.
    if spec.center_translate_amp_m > 0.0:
        w = 2.0 * np.pi * spec.center_translate_hz
        # World acceleration of a slow sinusoid centre motion.
        a_c = (
            -(w**2)
            * spec.center_translate_amp_m
            * np.stack(
                [
                    np.sin(w * t + 0.3),
                    np.cos(w * t + 0.7),
                    0.35 * np.sin(w * t + 1.1),
                ],
                axis=1,
            )
        )
        for i in range(n):
            R = so3.quat_to_rotmat(quats[i])
            a[i] = a[i] + R.T @ a_c[i]

    # 2) Wrist hinge: local angular rate + tangential accel about body x.
    if spec.wrist_hinge_amp_rad > 0.0:
        w_h = 2.0 * np.pi * spec.wrist_hinge_hz
        hinge = spec.wrist_hinge_amp_rad * np.sin(w_h * t)
        hinge_rate = spec.wrist_hinge_amp_rad * w_h * np.cos(w_h * t)
        hinge_alpha = -spec.wrist_hinge_amp_rad * (w_h**2) * np.sin(w_h * t)
        lever = 0.06  # m approximate palm offset
        g[:, 0] = g[:, 0] + hinge_rate
        # Tangential + centripetal in body y/z
        a[:, 1] = a[:, 1] + hinge_alpha * lever
        a[:, 2] = a[:, 2] - (hinge_rate**2) * lever
        meta["hinge_peak_rad"] = float(np.max(np.abs(hinge)))

    # 3) Mount slide along body y — treat as time-varying lever perturbation.
    if spec.mount_slide_amp_m > 0.0:
        slide = spec.mount_slide_amp_m * np.sin(2.0 * np.pi * 3.0 * t + rng.uniform(0, 6))
        # Approximate: sliding sensor sees extra Coriolis-like terms from omega x v_slide
        for i in range(n):
            v_slide_body = np.array([0.0, slide[i] * 2.0 * np.pi * 3.0, 0.0])
            a[i] = a[i] + 2.0 * np.cross(g[i], v_slide_body)

    # 4) Nonlinear impact: broadband spike not explained by rigid kinematics.
    if spec.impact_nonlinear_g > 0.0 and 0 <= impact_idx < n:
        spike = spec.impact_nonlinear_g * 9.80665
        # 3-sample triangular pulse with random body direction
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction) + 1e-12
        for k, wgt in ((-1, 0.4), (0, 1.0), (1, 0.4)):
            j = impact_idx + k
            if 0 <= j < n:
                a[j] = a[j] + wgt * spike * direction

    # Keep finite
    g = np.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0)
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    meta["pos_span_m"] = float(np.max(np.linalg.norm(pos - pos[0], axis=1)))
    return g, a, meta
