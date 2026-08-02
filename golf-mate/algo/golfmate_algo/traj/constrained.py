"""Constrained trajectory estimation: joint accel-bias / tilt-error least squares.

Model
-----
With estimated orientation ``R_est`` and a small unknown world tilt error
``delta`` plus a body-frame accelerometer bias ``b``,

    a_world(t) = R(t)(a_meas(t) - b) + g_world - [R(t) a_meas(t)]x delta

Velocity and position are linear functionals of the unknown
``x = [v0, b, delta]``, so zero-velocity (ZUPT) and displacement constraints at
the detected swing events become a single linear least-squares problem instead
of the ad-hoc piecewise de-trending used by the naive baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]


@dataclass
class ConstrainedTrajResult:
    positions: ArrayF
    velocities: ArrayF
    accel_bias_body: ArrayF
    tilt_error_world: ArrayF
    v0: ArrayF
    residual_norm: float


def _skew(v: ArrayF) -> ArrayF:
    return np.array(
        [[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]], dtype=np.float64
    )


def _cumtrapz(y: ArrayF, dt: float) -> ArrayF:
    out = np.zeros_like(y)
    if y.shape[0] > 1:
        out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * dt, axis=0)
    return out


def estimate_constrained_trajectory(
    quats: ArrayLike,
    accel: ArrayLike,
    dt: float,
    zupt_indices: list[int],
    *,
    zero_position_index: int | None = None,
    w_zupt: float = 1.0,
    w_pos: float = 1.0,
    ridge: float = 1e-9,
) -> ConstrainedTrajResult:
    """Solve for (v0, accel bias, tilt error) that best satisfy event constraints."""
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = quats.shape[0]
    if n < 3:
        raise ValueError("need >= 3 samples")
    zupt_indices = sorted({int(i) for i in zupt_indices if 0 <= int(i) < n})
    if not zupt_indices:
        raise ValueError("need at least one ZUPT index")

    Rs = np.zeros((n, 3, 3), dtype=np.float64)
    a_est = np.zeros((n, 3), dtype=np.float64)
    Jb = np.zeros((n, 3, 3), dtype=np.float64)  # d a_world / d b   = -R
    Jd = np.zeros((n, 3, 3), dtype=np.float64)  # d a_world / d delta = -[R a]x
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        Rs[i] = R
        a_est[i] = R @ accel[i] + so3.G_WORLD
        Jb[i] = -R
        Jd[i] = -_skew(R @ accel[i])

    # Integrate the nominal and each sensitivity channel
    V_nom = _cumtrapz(a_est, dt)
    P_nom = _cumtrapz(V_nom, dt)
    Vb = np.stack([_cumtrapz(Jb[:, :, k], dt) for k in range(3)], axis=2)  # (n,3,3)
    Vd = np.stack([_cumtrapz(Jd[:, :, k], dt) for k in range(3)], axis=2)
    Pb = np.stack([_cumtrapz(Vb[:, :, k], dt) for k in range(3)], axis=2)
    Pd = np.stack([_cumtrapz(Vd[:, :, k], dt) for k in range(3)], axis=2)

    t = np.arange(n, dtype=np.float64) * dt

    rows: list[ArrayF] = []
    rhs: list[ArrayF] = []

    # ZUPT rows: v0 + V_nom[i] + Vb[i] b + Vd[i] delta = 0
    for i in zupt_indices:
        A = np.zeros((3, 9), dtype=np.float64)
        A[:, 0:3] = np.eye(3)
        A[:, 3:6] = Vb[i]
        A[:, 6:9] = Vd[i]
        rows.append(w_zupt * A)
        rhs.append(w_zupt * (-V_nom[i]))

    # Position anchor: p(i0)=0 relative to first ZUPT (fixes v0 t drift)
    i0 = zero_position_index if zero_position_index is not None else zupt_indices[0]
    if len(zupt_indices) >= 2:
        iend = zupt_indices[-1]
        A = np.zeros((3, 9), dtype=np.float64)
        A[:, 0:3] = np.eye(3) * (t[iend] - t[i0])
        A[:, 3:6] = Pb[iend] - Pb[i0]
        A[:, 6:9] = Pd[iend] - Pd[i0]
        rows.append(w_pos * A)
        rhs.append(w_pos * (-(P_nom[iend] - P_nom[i0])))

    A_all = np.vstack(rows)
    b_all = np.concatenate(rhs)
    ATA = A_all.T @ A_all + ridge * np.eye(9)
    x = np.linalg.solve(ATA, A_all.T @ b_all)
    v0, bias, delta = x[0:3], x[3:6], x[6:9]

    vel = v0 + V_nom + Vb @ bias + Vd @ delta
    pos = np.outer(t - t[i0], v0) + P_nom + Pb @ bias + Pd @ delta
    pos = pos - pos[i0]

    residual = float(np.linalg.norm(A_all @ x - b_all))
    return ConstrainedTrajResult(
        positions=pos,
        velocities=vel,
        accel_bias_body=bias,
        tilt_error_world=delta,
        v0=v0,
        residual_norm=residual,
    )
