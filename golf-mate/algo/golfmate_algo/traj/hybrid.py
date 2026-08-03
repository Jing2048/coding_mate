"""Hybrid trajectory: varying centre + event constraints + plane closure.

Combines:
  A. Rigid lever arm with truncated SVD (baseline)
  B. Translating-centre detector via dead-reckon vs ``R L`` variance
  C. Soft blend toward constrained ZUPT trajectory when centre moves
  D. Soft projection onto swing-plane circle (SciRep-inspired)

Corrections are gated by the centre-variance detector so isomorphic analytic
swings (fixed centre) keep the rigid upper bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.signal import butter, filtfilt

from golfmate_algo.math import so3
from golfmate_algo.traj.constrained import estimate_constrained_trajectory
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.traj.swing_plane import fit_swing_plane
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]


def _skew(v: ArrayF) -> ArrayF:
    return np.array(
        [[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]],
        dtype=np.float64,
    )


def _lowpass(x: ArrayF, fs: float, cutoff_hz: float) -> ArrayF:
    if x.shape[0] < 16 or cutoff_hz <= 0:
        return x.copy()
    wn = min(cutoff_hz / (0.5 * fs), 0.99)
    if wn <= 0:
        return x.copy()
    b, a = butter(2, wn, btype="low")
    try:
        return filtfilt(b, a, x, axis=0)
    except ValueError:
        return x.copy()


@dataclass
class HybridTrajectoryResult:
    lever_arm_body: ArrayF
    radius_m: float
    center_world: ArrayF
    positions: ArrayF
    velocities: ArrayF
    residual_rms_m_s2: float
    rank: int
    valid: bool
    blend_w_lever: float
    plane_residual_rms: float
    circle_residual_rms: float
    center_harmonics: int
    fallback: float
    meta: dict[str, float] = field(default_factory=dict)


def _implied_center_variance(
    quats: ArrayF,
    accel: ArrayF,
    dt: float,
    phases: SwingPhases,
    L: ArrayF,
    cutoff_hz: float = 1.5,
) -> float:
    """RMS std of low-pass implied centre ``p_dr - R L`` (translating-centre score)."""
    _, _, pos_dr = reconstruct_trajectory(quats, accel, dt, phases=phases)
    Rs = np.stack([so3.quat_to_rotmat(q) for q in quats])
    pos_rel = np.einsum("nij,j->ni", Rs, L)
    c = pos_dr - pos_rel
    c = _lowpass(c, 1.0 / max(dt, 1e-6), cutoff_hz)
    return float(np.sqrt(np.mean(np.var(c, axis=0))))


def _plane_circle_blend(pos: ArrayF, lo: int, hi: int, blend: float) -> tuple[ArrayF, float, float]:
    plane = fit_swing_plane(pos[lo:hi])
    seg = pos[lo:hi]
    c = plane.centroid
    nrm = plane.normal
    ref = np.array([1.0, 0.0, 0.0]) if abs(nrm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(nrm, ref)
    e1 /= np.linalg.norm(e1) + 1e-12
    e2 = np.cross(nrm, e1)
    x_loc = seg - c
    x_p = x_loc - np.outer(x_loc @ nrm, nrm)
    uv = np.column_stack([x_p @ e1, x_p @ e2])
    center_uv = np.array(
        [np.dot(plane.center_3d - c, e1), np.dot(plane.center_3d - c, e2)]
    )
    vec = uv - center_uv
    norms = np.linalg.norm(vec, axis=1, keepdims=True) + 1e-12
    uv_c = center_uv + vec / norms * max(plane.radius, 1e-3)
    circ = c + uv_c[:, 0:1] * e1 + uv_c[:, 1:2] * e2
    out = pos.copy()
    out[lo:hi] = (1.0 - blend) * seg + blend * circ
    return out, float(plane.plane_residual_rms), float(plane.circle_residual_rms)


def _fourier_center_from_residual(
    quats: ArrayF,
    gyro: ArrayF,
    accel: ArrayF,
    L: ArrayF,
    dt: float,
    addr: int,
    fin: int,
    n_harmonics: int,
    gain: float,
) -> tuple[ArrayF, int]:
    """Low-order Fourier centre from residual world accel (L fixed)."""
    n = quats.shape[0]
    alpha = np.gradient(gyro, dt, axis=0)
    a_res = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        Sw = _skew(gyro[i])
        Sa = _skew(alpha[i])
        a_rigid = R @ ((Sa + Sw @ Sw) @ L)
        a_meas = R @ accel[i] + so3.G_WORLD
        a_res[i] = a_meas - a_rigid
    fs = 1.0 / max(dt, 1e-6)
    a_lp = _lowpass(a_res, fs, 2.5)
    t = np.arange(n, dtype=np.float64) * dt
    T = max(float(t[-1] - t[0]), 1e-3)
    theta = 2.0 * np.pi * (t - t[0]) / T
    n_harm = max(0, int(n_harmonics))
    a_c = a_lp
    used = 0
    if n_harm > 0:
        cols = []
        for k in range(1, n_harm + 1):
            cols.append(np.cos(k * theta))
            cols.append(np.sin(k * theta))
        B = np.column_stack(cols)
        try:
            coef, *_ = np.linalg.lstsq(B, a_lp, rcond=None)
            a_c = B @ coef
            used = n_harm
        except np.linalg.LinAlgError:
            pass
    vc = np.cumsum(a_c, axis=0) * dt
    rest = np.zeros(n, dtype=bool)
    rest[max(0, addr - max(1, int(0.1 / dt))) : addr + 1] = True
    rest[fin : min(n, fin + max(1, int(0.15 / dt)) + 1)] = True
    if rest.any():
        vc = vc - np.mean(vc[rest], axis=0, keepdims=True)
    c = np.cumsum(vc, axis=0) * dt
    c = c - c[addr]
    return gain * c, used


def estimate_hybrid_trajectory(
    quats: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    dt: float,
    phases: SwingPhases,
    *,
    n_harmonics: int = 2,
    center_var_threshold: float = 0.07,
    center_gain: float = 0.15,
    constrained_blend: float = 0.40,
    plane_blend: float = 0.15,
    max_residual_m_s2: float = 25.0,
) -> HybridTrajectoryResult:
    """Hybrid wrist trajectory reconstruction matching the pipeline contract."""
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = quats.shape[0]
    dt = float(dt)

    if n < 16:
        la = estimate_lever_arm(quats, gyro, accel, dt)
        return HybridTrajectoryResult(
            lever_arm_body=la.lever_arm_body,
            radius_m=la.radius_m,
            center_world=np.broadcast_to(la.center_world, (n, 3)).copy(),
            positions=la.positions,
            velocities=la.velocities,
            residual_rms_m_s2=la.residual_rms_m_s2,
            rank=la.rank,
            valid=la.valid,
            blend_w_lever=1.0,
            plane_residual_rms=0.0,
            circle_residual_rms=0.0,
            center_harmonics=0,
            fallback=1.0,
            meta={"reason_short_series": 1.0},
        )

    rigid = estimate_lever_arm(quats, gyro, accel, dt)
    L = rigid.lever_arm_body.copy()
    resid_rms = float(rigid.residual_rms_m_s2)
    rank = int(rigid.rank)
    addr = int(np.clip(phases.address_idx, 0, n - 1))
    top = int(np.clip(phases.top_idx, 0, n - 1))
    fin = int(np.clip(phases.finish_idx, 0, n - 1))

    pos_rel = np.zeros((n, 3), dtype=np.float64)
    vel_kin = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        pos_rel[i] = R @ L
        vel_kin[i] = R @ (_skew(gyro[i]) @ L)
    center0 = -pos_rel[addr]
    pos = pos_rel + center0
    vel = vel_kin.copy()

    c_var = _implied_center_variance(quats, accel, dt, phases, L)
    moving = c_var >= center_var_threshold
    # Also engage on very high rigid residual (violation stress)
    moving = moving or (resid_rms >= 12.0)

    w_cstr = 0.0
    n_harm_used = 0
    c_extra = np.zeros((n, 3), dtype=np.float64)
    plane_rms = 0.0
    circ_rms = 0.0
    apply_plane = False

    if moving:
        # B: slowly varying centre from residual accel Fourier
        c_extra, n_harm_used = _fourier_center_from_residual(
            quats, gyro, accel, L, dt, addr, fin, n_harmonics, center_gain
        )
        pos = pos + c_extra
        vel = vel + np.gradient(c_extra, dt, axis=0)

        # C: soft constrained event ZUPT blend
        try:
            zupt = sorted({addr, top, fin})
            constrained = estimate_constrained_trajectory(
                quats, accel, dt, zupt, zero_position_index=addr
            )
            pos_c = constrained.positions - constrained.positions[addr]
            # Match absolute level at address
            pos_c = pos_c + pos[addr]
            w_cstr = float(constrained_blend)
            if resid_rms >= 12.0:
                w_cstr = float(np.clip(constrained_blend + 0.15, 0.0, 0.6))
            pos = (1.0 - w_cstr) * pos + w_cstr * pos_c
            vel = np.gradient(pos, dt, axis=0)
        except (ValueError, np.linalg.LinAlgError):
            w_cstr = 0.0

        # D: soft plane / circle closure
        lo, hi = addr, min(n, fin + 1)
        if hi - lo >= 8 and plane_blend > 0:
            try:
                pos, plane_rms, circ_rms = _plane_circle_blend(pos, lo, hi, plane_blend)
                vel = np.gradient(pos, dt, axis=0)
                apply_plane = True
            except (ValueError, np.linalg.LinAlgError):
                pass

    w_lever = 1.0 - w_cstr
    valid = bool(rank >= 2 and resid_rms < max_residual_m_s2)
    return HybridTrajectoryResult(
        lever_arm_body=L.astype(np.float64),
        radius_m=float(np.linalg.norm(L)),
        center_world=(center0 + c_extra).astype(np.float64),
        positions=pos.astype(np.float64),
        velocities=vel.astype(np.float64),
        residual_rms_m_s2=resid_rms,
        rank=rank,
        valid=valid,
        blend_w_lever=float(w_lever),
        plane_residual_rms=float(plane_rms),
        circle_residual_rms=float(circ_rms),
        center_harmonics=int(n_harm_used),
        fallback=0.0,
        meta={
            "center_var": float(c_var),
            "center_var_threshold": float(center_var_threshold),
            "center_variation_on": float(1.0 if moving else 0.0),
            "constrained_blend": float(w_cstr),
            "center_gain": float(center_gain if moving else 0.0),
            "plane_blend_applied": float(1.0 if apply_plane else 0.0),
            "rigid_residual_m_s2": resid_rms,
        },
    )


estimate_trajectory_hybrid = estimate_hybrid_trajectory
