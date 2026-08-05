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

import math
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


def _finish_on_circle(
    pos: ArrayF, addr: int, fin: int, *, gain: float = 0.55
) -> tuple[ArrayF, float, float, float]:
    """SciRep-style soft project FIN onto the virtual swing-plane circle.

    Fits plane/circle on ``[addr, fin]``, projects ``pos[fin]`` onto the circle,
    then distributes the correction linearly from address→finish (analogue of
    their constant accel-bias re-integration that places FIN on the circle).
    """
    lo, hi = int(addr), int(fin) + 1
    if hi - lo < 8 or gain <= 0:
        return pos, 0.0, 0.0, 0.0
    plane = fit_swing_plane(pos[lo:hi])
    c = plane.centroid
    nrm = plane.normal
    ref = np.array([1.0, 0.0, 0.0]) if abs(nrm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(nrm, ref)
    e1 /= np.linalg.norm(e1) + 1e-12
    e2 = np.cross(nrm, e1)
    center_uv = np.array(
        [np.dot(plane.center_3d - c, e1), np.dot(plane.center_3d - c, e2)]
    )
    p_fin = pos[fin]
    # Project FIN onto plane then onto circle radius
    x = p_fin - c
    x_p = x - nrm * float(np.dot(x, nrm))
    uv = np.array([float(np.dot(x_p, e1)), float(np.dot(x_p, e2))])
    vec = uv - center_uv
    nrm_uv = float(np.linalg.norm(vec)) + 1e-12
    uv_c = center_uv + vec / nrm_uv * max(float(plane.radius), 1e-3)
    ep = c + uv_c[0] * e1 + uv_c[1] * e2
    delta = ep - p_fin
    corr = float(np.linalg.norm(delta))
    if corr < 1e-9:
        return pos, float(plane.plane_residual_rms), float(plane.circle_residual_rms), 0.0
    out = pos.copy()
    span = max(1, fin - addr)
    for k in range(addr, fin + 1):
        alpha = gain * ((k - addr) / span) ** 2  # quadratic ramp like double-int bias
        out[k] = out[k] + alpha * delta
    return out, float(plane.plane_residual_rms), float(plane.circle_residual_rms), corr


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


def _detect_strap_slip(
    quats: ArrayF,
    gyro: ArrayF,
    accel: ArrayF,
    dt: float,
    phases: SwingPhases,
    L: ArrayF,
) -> dict[str, float]:
    """Early vs late lever consistency — strap slip rotates/translates L mid-swing."""
    n = quats.shape[0]
    addr = int(np.clip(phases.address_idx, 0, n - 1))
    fin = int(np.clip(phases.finish_idx, 0, n - 1))
    if fin - addr < 24:
        return {
            "strap_slip_score": 0.0,
            "strap_slip_detected": 0.0,
            "lever_angle_delta_deg": 0.0,
            "radius_ratio": 1.0,
        }
    mid = addr + (fin - addr) // 2
    try:
        early = estimate_lever_arm(
            quats, gyro, accel, dt, active_slice=(addr, mid + 1)
        )
        late = estimate_lever_arm(
            quats, gyro, accel, dt, active_slice=(mid, fin + 1)
        )
    except (ValueError, np.linalg.LinAlgError):
        return {
            "strap_slip_score": 0.0,
            "strap_slip_detected": 0.0,
            "lever_angle_delta_deg": 0.0,
            "radius_ratio": 1.0,
        }
    Le = early.lever_arm_body
    Ll = late.lever_arm_body
    ne = float(np.linalg.norm(Le)) + 1e-12
    nl = float(np.linalg.norm(Ll)) + 1e-12
    cosang = float(np.clip(np.dot(Le, Ll) / (ne * nl), -1.0, 1.0))
    ang_deg = float(np.degrees(np.arccos(cosang)))
    ratio = float(max(ne, nl) / min(ne, nl))
    # Score in [0,1]: angle>~25° or radius ratio>~1.35 is suspicious.
    score_ang = float(np.clip((ang_deg - 12.0) / 30.0, 0.0, 1.0))
    score_r = float(np.clip((ratio - 1.15) / 0.5, 0.0, 1.0))
    # Also compare each half to the full-swing L.
    nL = float(np.linalg.norm(L)) + 1e-12
    cos_e = float(np.clip(np.dot(Le, L) / (ne * nL), -1.0, 1.0))
    cos_l = float(np.clip(np.dot(Ll, L) / (nl * nL), -1.0, 1.0))
    ang_full = max(
        float(np.degrees(np.arccos(cos_e))),
        float(np.degrees(np.arccos(cos_l))),
    )
    score_full = float(np.clip((ang_full - 15.0) / 30.0, 0.0, 1.0))
    score = float(np.clip(max(score_ang, score_r, score_full), 0.0, 1.0))
    # Require both angular change and that both halves had usable rank.
    usable = int(early.rank) >= 2 and int(late.rank) >= 2
    detected = float(1.0 if (usable and score >= 0.55) else 0.0)
    return {
        "strap_slip_score": score,
        "strap_slip_detected": detected,
        "lever_angle_delta_deg": ang_deg,
        "radius_ratio": ratio,
        "strap_slip_early_rank": float(early.rank),
        "strap_slip_late_rank": float(late.rank),
    }


def _apply_lever_prior(
    L: ArrayF,
    *,
    lever_prior_body: ArrayF | None,
    lever_prior_radius_m: float | None,
    rank: int,
    resid_rms: float,
) -> tuple[ArrayF, dict[str, float]]:
    """Optional personal lever/arm prior — soft blend; never worsens strong LS."""
    meta: dict[str, float] = {
        "lever_prior_applied": 0.0,
        "lever_prior_weight": 0.0,
        "lever_prior_radius_m": float("nan"),
    }
    prior: ArrayF | None = None
    if lever_prior_body is not None:
        prior = np.asarray(lever_prior_body, dtype=np.float64).reshape(3).copy()
    elif lever_prior_radius_m is not None and math.isfinite(float(lever_prior_radius_m)):
        r_prior = float(lever_prior_radius_m)
        if r_prior > 0.05:
            u = L / (float(np.linalg.norm(L)) + 1e-12)
            prior = (r_prior * u).astype(np.float64)
    if prior is None:
        return L, meta
    r_p = float(np.linalg.norm(prior))
    meta["lever_prior_radius_m"] = r_p
    # Strong LS (rank≥2, modest residual, plausible radius): light prior only.
    r_ls = float(np.linalg.norm(L))
    strong = rank >= 2 and resid_rms < 12.0 and 0.2 <= r_ls <= 1.4
    if strong:
        w = 0.15
    elif rank < 2 or resid_rms >= 18.0 or r_ls < 0.15 or r_ls > 1.6:
        w = 0.85
    else:
        w = 0.40
    L_out = ((1.0 - w) * L + w * prior).astype(np.float64)
    meta["lever_prior_applied"] = 1.0
    meta["lever_prior_weight"] = float(w)
    return L_out, meta


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
    lever_prior_body: ArrayLike | None = None,
    lever_prior_radius_m: float | None = None,
    enable_strap_slip_detect: bool = True,
) -> HybridTrajectoryResult:
    """Hybrid wrist trajectory reconstruction matching the pipeline contract.

    SciRep-inspired upgrades (Kim & Park, SciRep 2024; extreme-algo):
    * Event ZUPT at ADD/BST/FIN via constrained LS blend
    * Soft plane/circle blend on the translating-centre path
    * Finish-on-circle soft closure (project FIN residual onto virtual circle)
    * Rigidity-failure flagged in meta (club-mount casting) without DR replace —
      pure DR under consumer noise often exceeds broken-lever error

    Optional commercial inputs (backward compatible defaults):
    * ``lever_prior_body`` / ``lever_prior_radius_m`` — personal lever/arm prior
    * ``enable_strap_slip_detect`` — early/late lever consistency indicator
    """
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

    addr = int(np.clip(phases.address_idx, 0, n - 1))
    top = int(np.clip(phases.top_idx, 0, n - 1))
    fin = int(np.clip(phases.finish_idx, 0, n - 1))
    imp = int(np.clip(phases.impact_idx, 0, n - 1))

    # Default lever LS (ω²-weighted inside estimate_lever_arm).
    rigid = estimate_lever_arm(quats, gyro, accel, dt)
    L = rigid.lever_arm_body.copy()
    resid_rms = float(rigid.residual_rms_m_s2)
    rank = int(rigid.rank)

    prior_meta: dict[str, float] = {}
    L, prior_meta = _apply_lever_prior(
        L,
        lever_prior_body=(
            np.asarray(lever_prior_body, dtype=np.float64).reshape(3)
            if lever_prior_body is not None
            else None
        ),
        lever_prior_radius_m=lever_prior_radius_m,
        rank=rank,
        resid_rms=resid_rms,
    )

    strap_meta = (
        _detect_strap_slip(quats, gyro, accel, dt, phases, L)
        if enable_strap_slip_detect
        else {
            "strap_slip_score": 0.0,
            "strap_slip_detected": 0.0,
            "lever_angle_delta_deg": 0.0,
            "radius_ratio": 1.0,
        }
    )

    pos_rel = np.zeros((n, 3), dtype=np.float64)
    vel_kin = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        pos_rel[i] = R @ L
        vel_kin[i] = R @ (_skew(gyro[i]) @ L)
    center0 = -pos_rel[addr]
    pos = pos_rel + center0
    vel = vel_kin.copy()

    # Rigidity-failure detector (club-mount casting) — meta + kinematic fallback.
    _, _, pos_dr = reconstruct_trajectory(quats, accel, dt, phases=phases)
    span_dr = float(np.max(np.linalg.norm(pos_dr - pos_dr[addr], axis=1)))
    span_lever = float(np.max(np.linalg.norm(pos - pos[addr], axis=1)))
    radius = float(np.linalg.norm(L))
    rigidity_fail = (
        (resid_rms >= 12.0 and span_dr > 0.8 and span_lever < 0.70 * span_dr)
        or (resid_rms >= 15.0 and radius < 0.95 and span_dr > 1.0)
        or (radius < 0.35 and span_dr > 1.2 and span_lever < 0.50 * span_dr)
    )

    # Casting / distal-mount: lever LS collapses to a short radius while path span
    # is large. Pure DR often explodes under consumer noise — replace with a
    # club-scale rigid prior along the estimated lever direction (r≈1.0 m), then
    # soft plane/circle closure. Wrist-mount product path rarely trips this.
    if rigidity_fail and radius < 0.70:
        u = L / (radius + 1e-12)
        r_prior = 1.0  # forearm+club scale (casting_pathology / club mount)
        L = (r_prior * u).astype(np.float64)
        for i in range(n):
            R = so3.quat_to_rotmat(quats[i])
            pos_rel[i] = R @ L
            vel_kin[i] = R @ (_skew(gyro[i]) @ L)
        center0 = -pos_rel[addr]
        pos = pos_rel + center0
        vel = vel_kin.copy()
        radius = r_prior
        # Soft plane closure on the prior circle
        lo, hi = addr, min(n, fin + 1)
        plane_rms = 0.0
        circ_rms = 0.0
        if hi - lo >= 8:
            try:
                pos, plane_rms, circ_rms = _plane_circle_blend(pos, lo, hi, 0.25)
                vel = np.gradient(pos, dt, axis=0)
            except (ValueError, np.linalg.LinAlgError):
                pass
        return HybridTrajectoryResult(
            lever_arm_body=L,
            radius_m=float(radius),
            center_world=np.broadcast_to(center0, (n, 3)).copy(),
            positions=pos.astype(np.float64),
            velocities=vel.astype(np.float64),
            residual_rms_m_s2=resid_rms,
            rank=rank,
            valid=False,
            blend_w_lever=1.0,
            plane_residual_rms=float(plane_rms),
            circle_residual_rms=float(circ_rms),
            center_harmonics=0,
            fallback=1.0,
            meta={
                "center_var": 0.0,
                "center_var_threshold": float(center_var_threshold),
                "center_variation_on": 0.0,
                "constrained_blend": 0.0,
                "center_gain": 0.0,
                "plane_blend_applied": float(1.0 if plane_rms or circ_rms else 0.0),
                "finish_circle_corr_m": 0.0,
                "rigid_residual_m_s2": resid_rms,
                "rigidity_fail": 1.0,
                "rigidity_prior_radius_m": float(r_prior),
                "span_dr_m": float(span_dr),
                "span_lever_m": float(span_lever),
                "active_slice_top": float(top),
                "active_slice_imp": float(imp),
                "active_slice_fin": float(fin),
                **prior_meta,
                **strap_meta,
            },
        )

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
            # Sanity: reject constrained if it explodes vs lever path length
            span_l = float(np.max(np.linalg.norm(pos - pos[addr], axis=1))) + 1e-6
            span_c = float(np.max(np.linalg.norm(pos_c - pos_c[addr], axis=1)))
            # Reject constrained only when the rigid lever path has collapsed
            # (typical of bad external AHRS) while the ZUPT path explodes.
            lever_collapsed = span_l < 0.25 and float(rigid.radius_m) < 0.30
            if (lever_collapsed and span_c > 1.5) or span_c > 12.0:
                w_cstr = 0.0
            else:
                w_cstr = float(constrained_blend)
                if resid_rms >= 12.0:
                    w_cstr = float(np.clip(constrained_blend + 0.15, 0.0, 0.6))
                pos = (1.0 - w_cstr) * pos + w_cstr * pos_c
                vel = np.gradient(pos, dt, axis=0)
        except (ValueError, np.linalg.LinAlgError):
            w_cstr = 0.0

        # D: soft plane / circle closure (SciRep virtual-circle prior)
        lo, hi = addr, min(n, fin + 1)
        if hi - lo >= 8 and plane_blend > 0 and w_cstr > 0:
            try:
                pos, plane_rms, circ_rms = _plane_circle_blend(pos, lo, hi, plane_blend)
                vel = np.gradient(pos, dt, axis=0)
                apply_plane = True
            except (ValueError, np.linalg.LinAlgError):
                pass

        # E: SciRep finish-on-circle — soft-project FIN onto the fitted circle,
        # then distribute the correction linearly from ADD→FIN (accel-bias analogue).
        if hi - lo >= 8:
            try:
                pos, plane_rms2, circ_rms2, fin_corr = _finish_on_circle(
                    pos, addr, fin, gain=0.55
                )
                if fin_corr > 1e-6:
                    vel = np.gradient(pos, dt, axis=0)
                    plane_rms = max(plane_rms, plane_rms2)
                    circ_rms = max(circ_rms, circ_rms2)
                    apply_plane = True
            except (ValueError, np.linalg.LinAlgError):
                fin_corr = 0.0
        else:
            fin_corr = 0.0

        span_hy = float(np.max(np.linalg.norm(pos - pos[addr], axis=1)))
        if span_hy > 12.0:
            pos = pos_rel + center0
            vel = vel_kin.copy()
            c_extra = np.zeros((n, 3), dtype=np.float64)
            w_cstr = 0.0
            n_harm_used = 0
            apply_plane = False
            plane_rms = 0.0
            circ_rms = 0.0
            fin_corr = 0.0
            fallback = 1.0
        else:
            fallback = 0.0
    else:
        fallback = 0.0
        fin_corr = 0.0

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
        fallback=float(fallback),
        meta={
            "center_var": float(c_var),
            "center_var_threshold": float(center_var_threshold),
            "center_variation_on": float(1.0 if moving else 0.0),
            "constrained_blend": float(w_cstr),
            "center_gain": float(center_gain if moving else 0.0),
            "plane_blend_applied": float(1.0 if apply_plane else 0.0),
            "finish_circle_corr_m": float(fin_corr),
            "rigid_residual_m_s2": resid_rms,
            "rigidity_fail": float(1.0 if rigidity_fail else 0.0),
            "span_dr_m": float(span_dr),
            "span_lever_m": float(span_lever),
            "active_slice_top": float(top),
            "active_slice_imp": float(imp),
            "active_slice_fin": float(fin),
            **prior_meta,
            **strap_meta,
        },
    )


estimate_trajectory_hybrid = estimate_hybrid_trajectory
