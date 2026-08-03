"""Offline SO(3) smoother: forward AHRS + endpoint rest anchors.

Six-axis swing records are short (~1–2 s) and almost always bookended by quiet
address / finish windows. A causal filter cannot use finish information to
correct earlier tilt; an offline pass can.

Approach
--------
1. Take a forward orientation estimate (any AHRS).
2. Measure tilt at address and finish from the accelerometer (gravity).
3. Build world-tilt corrections at both anchors (yaw left untouched).
4. Geodesically blend those corrections along the record with a smoothstep
   weight keyed to phase progress address→finish.

This is a single elegant correction — no second filter tuning, no covariance
bookkeeping — and it is a no-op when anchors already agree with the forward
estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.ahrs.suite import DynamicsGate, IDENTITY_QUAT, quat_slerp
from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]

G_NORM = float(np.linalg.norm(so3.G_WORLD))
UP_WORLD = -so3.G_WORLD / G_NORM


@dataclass
class OfflineSmoothResult:
    quats: ArrayF
    addr_tilt_corr_deg: float
    fin_tilt_corr_deg: float
    applied: bool


def _tilt_correction_quat(q: ArrayLike, accel: ArrayLike) -> ArrayF:
    """World-left tilt quaternion that maps measured up → world up."""
    q_in = so3.normalize_quat(q)
    a = np.asarray(accel, dtype=np.float64).reshape(3)
    n = float(np.linalg.norm(a))
    if not np.isfinite(n) or n < 1e-9:
        return IDENTITY_QUAT.copy()
    a_hat = a / n
    measured_up_world = so3.quat_to_rotmat(q_in) @ a_hat
    return so3.quat_from_two_vectors(measured_up_world, UP_WORLD)


def _angle_deg(q: ArrayLike) -> float:
    q = so3.normalize_quat(q)
    return float(2.0 * np.degrees(np.arccos(float(np.clip(abs(q[0]), 0.0, 1.0)))))


def _smoothstep(x: ArrayF) -> ArrayF:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _rest_ok(gyro: ArrayF, accel: ArrayF, gate: DynamicsGate, dt: float) -> bool:
    if gyro.shape[0] < 1:
        return False
    g_n = float(np.mean(np.linalg.norm(gyro, axis=1)))
    a_n = float(np.mean(np.linalg.norm(accel, axis=1)))
    # Prefer the dynamics gate, but fall back to a magnitude check so lightly
    # disturbed finish holds still qualify as anchors.
    if gyro.shape[0] >= 2 and dt > 0:
        alpha = float(np.mean(np.linalg.norm(np.diff(gyro, axis=0), axis=1) / dt))
    else:
        alpha = 0.0
    if gate(g_n, a_n, alpha) > 0.15:
        return True
    return g_n < 0.6 and abs(a_n - G_NORM) < 3.5


def _scale_quat_angle(q: ArrayF, max_deg: float) -> ArrayF:
    """Clamp a rotation quaternion's angle to ``max_deg``."""
    q = so3.normalize_quat(q)
    if q[0] < 0.0:
        q = -q
    ang = float(2.0 * np.arccos(float(np.clip(q[0], -1.0, 1.0))))
    max_rad = float(np.deg2rad(max_deg))
    if ang <= max_rad or ang < 1e-12:
        return q
    axis = q[1:] / (np.linalg.norm(q[1:]) + 1e-15)
    return so3.quat_from_axis_angle(axis, max_rad)


def smooth_endpoint_anchors(
    quats: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    dt: float,
    *,
    address_idx: int,
    finish_idx: int,
    max_corr_deg: float = 20.0,
) -> OfflineSmoothResult:
    """Apply geodesic endpoint tilt anchors to a forward orientation track."""
    q = np.asarray(quats, dtype=np.float64).reshape(-1, 4).copy()
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = q.shape[0]
    if n < 8:
        return OfflineSmoothResult(q, 0.0, 0.0, False)

    addr = int(np.clip(address_idx, 0, n - 1))
    fin = int(np.clip(finish_idx, addr + 1, n - 1))
    dt = float(max(dt, 1e-6))
    gate = DynamicsGate()

    # Average a short rest neighbourhood around each anchor. Prefer the quietest
    # sample in a neighbourhood of finish (phase labels can sit on residual rate).
    w_addr = max(1, int(0.05 / dt))
    w_fin = max(1, int(0.12 / dt))
    a0, a1 = max(0, addr - w_addr), min(n, addr + w_addr + 1)
    f0, f1 = max(addr + 1, fin - w_fin // 4), min(n, fin + w_fin + 1)
    # Pick the quietest accel-norm window centre near finish
    if f1 - f0 >= 3:
        acc_n = np.linalg.norm(accel[f0:f1], axis=1)
        gyro_n = np.linalg.norm(gyro[f0:f1], axis=1)
        score = np.abs(acc_n - G_NORM) + 2.0 * gyro_n
        fin = f0 + int(np.argmin(score))
        f0, f1 = max(0, fin - w_fin // 3), min(n, fin + w_fin // 2 + 1)

    if not (
        _rest_ok(gyro[a0:a1], accel[a0:a1], gate, dt)
        or _rest_ok(gyro[f0:f1], accel[f0:f1], gate, dt)
    ):
        return OfflineSmoothResult(q, 0.0, 0.0, False)

    q_corr_addr = _tilt_correction_quat(q[addr], np.mean(accel[a0:a1], axis=0))
    use_fin = _rest_ok(gyro[f0:f1], accel[f0:f1], gate, dt)
    if use_fin:
        q_corr_fin = _tilt_correction_quat(q[fin], np.mean(accel[f0:f1], axis=0))
    else:
        # Finish not quiet enough for gravity — hold the address correction.
        q_corr_fin = q_corr_addr.copy()
    ang_a = _angle_deg(q_corr_addr)
    ang_f = _angle_deg(q_corr_fin)
    # Clamp oversized corrections (bad rest) rather than refusing — still helps.
    q_corr_addr = _scale_quat_angle(q_corr_addr, max_corr_deg)
    q_corr_fin = _scale_quat_angle(q_corr_fin, max_corr_deg)
    if ang_a < 0.15 and ang_f < 0.15:
        return OfflineSmoothResult(q, ang_a, ang_f, False)

    # Progress coordinate: 0 at address, 1 at finish (clamped outside)
    idx = np.arange(n, dtype=np.float64)
    progress = (idx - addr) / max(float(fin - addr), 1.0)
    w = _smoothstep(progress)

    out = np.zeros_like(q)
    for i in range(n):
        q_off = quat_slerp(q_corr_addr, q_corr_fin, float(w[i]))
        out[i] = so3.normalize_quat(so3.quat_multiply(q_off, q[i]))
        if i:
            out[i] = so3.ensure_quat_hemisphere(out[i], out[i - 1])
    return OfflineSmoothResult(out, ang_a, ang_f, True)
