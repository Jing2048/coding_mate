"""Drift-free trajectory via rigid lever-arm estimation.

Key idea
--------
During a golf swing the wrist sensor is, to good approximation, a point rigidly
offset from a slowly-moving rotation centre. Writing the sensor position as

    p(t) = c + R(t) L,        c constant, L body-fixed lever arm

and differentiating twice gives the specific force measured by the accelerometer

    f(t) = ([w]x[w]x + [alpha]x) L - R(t)^T g_world

which is **linear in L**. Solving that least-squares problem recovers the swing
radius and the full path from orientation alone, so the estimate never
accumulates double-integration drift. Integration-based dead reckoning is kept
as a baseline in ``dead_reckon`` for benchmarking.

The residual of the linear fit doubles as a validity metric: it grows when the
rigid-rotation assumption breaks (centre translating, wrist hinging hard).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]


@dataclass
class LeverArmResult:
    lever_arm_body: ArrayF  # (3,) L
    radius_m: float
    center_world: ArrayF  # (3,) c
    positions: ArrayF  # (N,3)
    velocities: ArrayF  # (N,3)
    residual_rms_m_s2: float
    condition_number: float
    rank: int
    unobservable_directions: ArrayF
    valid: bool


def _skew(v: ArrayF) -> ArrayF:
    return np.array(
        [[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]], dtype=np.float64
    )


def estimate_lever_arm(
    quats: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    dt: float,
    *,
    weight: ArrayLike | None = None,
    ridge: float = 1e-6,
    rank_tol: float = 1e-2,
    max_residual_m_s2: float = 25.0,
    active_slice: tuple[int, int] | None = None,
    huber_delta: float = 0.0,
) -> LeverArmResult:
    """Least-squares solve for the body-fixed lever arm and rebuild the path.

    Parameters
    ----------
    quats : (N,4) orientation estimates, body → world, [w,x,y,z]
    gyro : (N,3) body angular rate, rad/s
    accel : (N,3) specific force in body frame, m/s^2
    weight : optional (N,) sample weights; use to emphasise the high-signal
        downswing where the rigid model is most informative.
    ridge : Tikhonov regularisation on L.
    """
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = quats.shape[0]
    if n < 5:
        raise ValueError("need >= 5 samples")

    alpha = np.gradient(gyro, dt, axis=0)

    if weight is None:
        # Emphasise samples with meaningful rotation: information about L scales
        # with |w|^2 and |alpha|.
        w_mag = np.linalg.norm(gyro, axis=1)
        weight = w_mag**2 + np.linalg.norm(alpha, axis=1)
    weight = np.asarray(weight, dtype=np.float64).reshape(-1)
    # Optional phase window (e.g. top→finish): outside → near-zero weight.
    if active_slice is not None:
        lo, hi = active_slice
        lo = int(np.clip(lo, 0, n))
        hi = int(np.clip(hi, lo + 1, n))
        mask = np.zeros(n, dtype=np.float64)
        mask[lo:hi] = 1.0
        # Soft shoulders so the window edge is not a hard discontinuity.
        shoulder = max(1, int(0.03 / max(dt, 1e-6)))
        for k in range(shoulder):
            a = (k + 1) / (shoulder + 1)
            if lo - shoulder + k >= 0:
                mask[lo - shoulder + k] = max(mask[lo - shoulder + k], a)
            if hi + k < n:
                mask[hi + k] = max(mask[hi + k], 1.0 - a)
        weight = weight * mask
    weight = weight / (np.max(weight) + 1e-12)

    A = np.zeros((3 * n, 3), dtype=np.float64)
    b = np.zeros(3 * n, dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        Sw = _skew(gyro[i])
        Sa = _skew(alpha[i])
        Ai = Sw @ Sw + Sa
        bi = accel[i] + R.T @ so3.G_WORLD
        sw = np.sqrt(weight[i])
        A[3 * i : 3 * i + 3, :] = sw * Ai
        b[3 * i : 3 * i + 3] = sw * bi

    # Truncated SVD instead of a plain normal-equation solve. For a swing that
    # rotates about a fixed axis, translating the sensor *along* that axis does
    # not change its acceleration, so that component of L is unobservable and
    # the normal matrix is numerically singular. Ridge regression would still
    # let sensor noise excite the null direction; truncation removes it.
    # The discarded component only shifts the path by a constant world offset,
    # which cancels once the trajectory is referenced to address.
    U, s, Vt = np.linalg.svd(A, full_matrices=False)
    s_max = float(s[0]) if s.size else 0.0
    tol = max(rank_tol * s_max, 1e-12)
    keep = s > tol
    s_inv = np.zeros_like(s)
    s_inv[keep] = 1.0 / (s[keep] + ridge * s_max)
    L = Vt.T @ (s_inv * (U.T @ b))

    # One IRLS Huber reweight pass: down-weight samples that violate rigidity.
    if huber_delta > 0 and np.any(weight > 0):
        resid_v = (A @ L - b).reshape(-1, 3)
        r_n = np.linalg.norm(resid_v, axis=1)
        w_h = np.ones(n, dtype=np.float64)
        big = r_n > huber_delta
        w_h[big] = huber_delta / (r_n[big] + 1e-12)
        weight2 = weight * w_h
        weight2 = weight2 / (np.max(weight2) + 1e-12)
        for i in range(n):
            sw = np.sqrt(weight2[i])
            # Rebuild rows (Ai, bi already scaled by old sw — redo from scratch)
            R = so3.quat_to_rotmat(quats[i])
            Sw = _skew(gyro[i])
            Sa = _skew(alpha[i])
            Ai = Sw @ Sw + Sa
            bi = accel[i] + R.T @ so3.G_WORLD
            A[3 * i : 3 * i + 3, :] = sw * Ai
            b[3 * i : 3 * i + 3] = sw * bi
        U, s, Vt = np.linalg.svd(A, full_matrices=False)
        s_max = float(s[0]) if s.size else 0.0
        tol = max(rank_tol * s_max, 1e-12)
        keep = s > tol
        s_inv = np.zeros_like(s)
        s_inv[keep] = 1.0 / (s[keep] + ridge * s_max)
        L = Vt.T @ (s_inv * (U.T @ b))

    rank = int(np.count_nonzero(keep))
    cond = float(s_max / s[keep][-1]) if rank else float("inf")
    unobservable = Vt[rank:] if rank < 3 else np.zeros((0, 3), dtype=np.float64)

    resid = A @ L - b
    resid_rms = float(np.sqrt(np.mean(resid**2)))

    # Rebuild kinematics from orientation only
    pos_rel = np.zeros((n, 3), dtype=np.float64)
    vel = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        pos_rel[i] = R @ L
        vel[i] = R @ (_skew(gyro[i]) @ L)

    center = -pos_rel[0]
    positions = pos_rel + center

    return LeverArmResult(
        lever_arm_body=L,
        radius_m=float(np.linalg.norm(L)),
        center_world=center,
        positions=positions,
        velocities=vel,
        residual_rms_m_s2=resid_rms,
        condition_number=cond,
        rank=rank,
        unobservable_directions=unobservable,
        valid=bool(rank >= 2 and resid_rms < max_residual_m_s2),
    )
