"""Wrist kinematic features from phases, omega, and trajectory."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.math import so3
from golfmate_algo.traj.swing_plane import fit_swing_plane
from golfmate_algo.types import SwingPhases, WristFeatures


def compute_wrist_features(
    t: ArrayLike,
    gyro: ArrayLike,
    quats: ArrayLike,
    velocities: ArrayLike,
    positions: ArrayLike,
    phases: SwingPhases,
) -> WristFeatures:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    velocities = np.asarray(velocities, dtype=np.float64).reshape(-1, 3)
    positions = np.asarray(positions, dtype=np.float64).reshape(-1, 3)

    a, top, imp, fin = (
        phases.address_idx,
        phases.top_idx,
        phases.impact_idx,
        phases.finish_idx,
    )
    backswing_s = float(t[top] - t[a])
    downswing_s = float(t[imp] - t[top])
    tempo_s = float(t[imp] - t[a])
    rhythm = backswing_s / max(downswing_s, 1e-9)

    omega = np.linalg.norm(gyro, axis=1)
    # Peak omega in downswing window (top→impact), else global mid
    lo, hi = top, max(imp, top + 1)
    local = omega[lo : hi + 1]
    peak_rel = int(np.argmax(local))
    peak_idx = lo + peak_rel
    peak_omega = float(omega[peak_idx])
    peak_to_impact = float(t[imp] - t[peak_idx])

    speed = np.linalg.norm(velocities, axis=1)
    hand_speed_peak = float(speed[lo : fin + 1].max()) if fin > lo else float(speed.max())

    mask = np.zeros(len(t), dtype=bool)
    mask[a : fin + 1] = True
    plane = fit_swing_plane(positions, mask=mask)

    # Closure rate proxy: relative yaw about plane normal in pre-impact window
    pre = max(a, imp - max(3, (imp - top) // 3))
    q0 = quats[a]
    yaws = []
    for i in range(pre, imp + 1):
        # relative rotation from address
        q_rel = so3.quat_multiply(so3.quat_conjugate(q0), quats[i])
        # extract twist about plane normal approximated via vector part projected
        yaws.append(2.0 * float(np.arctan2(np.linalg.norm(q_rel[1:]), q_rel[0])))
    yaws_arr = np.asarray(yaws, dtype=np.float64)
    dt = float(t[imp] - t[pre]) if imp > pre else 1e-9
    closure_rate = float((yaws_arr[-1] - yaws_arr[0]) / dt) if len(yaws_arr) > 1 else 0.0

    return WristFeatures(
        tempo_s=tempo_s,
        backswing_s=backswing_s,
        downswing_s=downswing_s,
        rhythm=rhythm,
        peak_omega_rad_s=peak_omega,
        peak_omega_idx=peak_idx,
        peak_omega_to_impact_s=peak_to_impact,
        hand_speed_peak_m_s=hand_speed_peak,
        plane_angle_deg=plane.plane_angle_deg,
        closure_rate_rad_s=closure_rate,
        extras={
            "plane_residual_rms": plane.plane_residual_rms,
            "circle_residual_rms": plane.circle_residual_rms,
            "plane_radius_m": plane.radius,
        },
    )
