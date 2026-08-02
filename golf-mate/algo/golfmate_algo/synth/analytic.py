"""Analytic swing generators with closed-form ground truth.

The swing is driven by an **angular-velocity profile built from Gaussian basis
functions**, so angle, rate and angular acceleration are all available in closed
form (the angle is the error function). This matters: a generator that stitches
position splines together can introduce discontinuous angular acceleration,
which is an unphysical broadband transient that would flatter or defeat an
impact detector for the wrong reason.

Amplitudes are solved from two linear constraints - reach the top angle at the
top, and return to the ball at impact - so the geometry closes exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.special import erf

from golfmate_algo.math import so3
from golfmate_algo.types import ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]

G = 9.80665


@dataclass
class AnalyticRotationTruth:
    packet: ImuPacket
    quats_true: ArrayF
    omega_axis: ArrayF
    omega_rate: float


def constant_rate_rotation(
    fs_hz: float = 200.0,
    duration_s: float = 1.0,
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    rate_rad_s: float = 2.0,
    g: float = G,
) -> AnalyticRotationTruth:
    """IMU in pure constant-rate rotation about ``axis`` with no translation."""
    n = int(round(duration_s * fs_hz))
    dt = 1.0 / fs_hz
    t = np.arange(n, dtype=np.float64) * dt
    axis_v = np.asarray(axis, dtype=np.float64)
    axis_v = axis_v / (np.linalg.norm(axis_v) + 1e-12)
    omega = axis_v * rate_rad_s

    quats = np.zeros((n, 4), dtype=np.float64)
    gyro = np.tile(omega, (n, 1))
    accel = np.zeros((n, 3), dtype=np.float64)
    q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    for i in range(n):
        quats[i] = q
        R = so3.quat_to_rotmat(q)
        accel[i] = -R.T @ np.array([0.0, 0.0, -g])
        q = so3.integrate_gyro_rk4(q, omega, dt)

    packet = ImuPacket(
        frame=SensorFrame(fs_hz=fs_hz, wrist=WristSide.LEAD), t=t, gyro=gyro, accel=accel
    )
    return AnalyticRotationTruth(
        packet=packet, quats_true=quats, omega_axis=axis_v, omega_rate=rate_rad_s
    )


@dataclass
class SyntheticSwing:
    packet: ImuPacket
    phases_true: SwingPhases
    quats_true: ArrayF
    positions_true: ArrayF
    velocities_true: ArrayF
    angles: ArrayF
    omega_scalar: ArrayF
    alpha_scalar: ArrayF
    peak_omega_time_s: float
    impact_time_s: float
    casting: bool
    meta: dict[str, float]


def _gauss(t: ArrayF, mu: float, sigma: float) -> ArrayF:
    return np.exp(-0.5 * ((t - mu) / sigma) ** 2)


def _gauss_int(t: ArrayF, t0: float, mu: float, sigma: float) -> ArrayF:
    """Integral of ``_gauss`` from ``t0`` to ``t``."""
    c = sigma * np.sqrt(np.pi / 2.0)
    return c * (erf((t - mu) / (sigma * np.sqrt(2.0))) - erf((t0 - mu) / (sigma * np.sqrt(2.0))))


def _gauss_deriv(t: ArrayF, mu: float, sigma: float) -> ArrayF:
    return -((t - mu) / sigma**2) * _gauss(t, mu, sigma)


def planar_circular_swing(
    fs_hz: float = 200.0,
    radius_m: float = 0.45,
    *,
    address_s: float = 0.30,
    backswing_s: float = 0.75,
    downswing_s: float = 0.25,
    finish_s: float = 0.55,
    top_angle_deg: float = 110.0,
    plane_tilt_deg: float = 55.0,
    casting: bool = False,
    casting_lead_s: float = 0.09,
    impact_shock_g: float = 30.0,
    shock_ring_hz: float = 55.0,
    shock_decay_s: float = 0.012,
    g: float = G,
) -> SyntheticSwing:
    """Generate a tilted-plane circular wrist swing with closed-form truth.

    Parameters
    ----------
    casting : if True the downswing rate peaks ``casting_lead_s`` before impact
        (early release) instead of at impact.
    plane_tilt_deg : inclination of the swing plane from horizontal.
    impact_shock_g : amplitude of the damped broadband strike transient.
    """
    dt = 1.0 / fs_hz
    total_s = address_s + backswing_s + downswing_s + finish_s
    n = int(round(total_s * fs_hz))
    t = np.arange(n, dtype=np.float64) * dt

    t_addr = address_s
    t_top_nom = address_s + backswing_s
    t_impact = t_top_nom + downswing_s

    theta_top = np.deg2rad(top_angle_deg)

    mu1 = t_addr + 0.55 * backswing_s
    sig1 = backswing_s / 4.5
    lead = casting_lead_s if casting else 0.0
    mu2 = t_impact - lead
    sig2 = downswing_s / 2.2

    # Solve amplitudes from: theta(t_top_nom) = theta_top, theta(t_impact) = 0
    t0 = 0.0
    M = np.array(
        [
            [
                float(_gauss_int(np.array([t_top_nom]), t0, mu1, sig1)[0]),
                float(_gauss_int(np.array([t_top_nom]), t0, mu2, sig2)[0]),
            ],
            [
                float(_gauss_int(np.array([t_impact]), t0, mu1, sig1)[0]),
                float(_gauss_int(np.array([t_impact]), t0, mu2, sig2)[0]),
            ],
        ],
        dtype=np.float64,
    )
    rhs = np.array([theta_top, 0.0], dtype=np.float64)
    A = np.linalg.solve(M, rhs)
    a1, a2 = float(A[0]), float(A[1])

    omega_s = a1 * _gauss(t, mu1, sig1) + a2 * _gauss(t, mu2, sig2)
    theta = a1 * _gauss_int(t, t0, mu1, sig1) + a2 * _gauss_int(t, t0, mu2, sig2)
    alpha_s = a1 * _gauss_deriv(t, mu1, sig1) + a2 * _gauss_deriv(t, mu2, sig2)

    # True events: top is the rate reversal; impact is where the angle returns to 0
    impact_idx = int(np.argmin(np.abs(t - t_impact)))
    sign_change = np.where(np.sign(omega_s[:-1]) != np.sign(omega_s[1:]))[0]
    before_impact = sign_change[sign_change < impact_idx]
    top_idx = int(before_impact[-1]) if before_impact.size else int(round(t_top_nom * fs_hz))

    # Address and finish are the outer edges of motion. They must be measured
    # relative to each half's own rate peak: the rate also passes through zero at
    # the top, so a naive "last quiet sample before the top" lands on the top.
    quiet = np.abs(omega_s) < 0.04 * np.max(np.abs(omega_s))
    bs_peak = int(np.argmax(np.abs(omega_s[: max(top_idx, 1)])))
    address_idx = 0
    for i in range(bs_peak):
        if quiet[i]:
            address_idx = i
    fw_peak = impact_idx + int(np.argmax(np.abs(omega_s[impact_idx:])))
    finish_idx = n - 1
    for i in range(n - 1, fw_peak, -1):
        if quiet[i]:
            finish_idx = i
    finish_idx = max(finish_idx, impact_idx + 2)

    # Plane geometry: rotate the nominal YZ circle about the world Y axis
    tilt = np.deg2rad(90.0 - plane_tilt_deg)
    ct, st = np.cos(tilt), np.sin(tilt)
    R_plane = np.array([[ct, 0.0, st], [0.0, 1.0, 0.0], [-st, 0.0, ct]], dtype=np.float64)
    normal_world = R_plane @ np.array([1.0, 0.0, 0.0])

    s, c = np.sin(theta), np.cos(theta)
    p_plane = radius_m * np.stack([np.zeros_like(s), s, -c], axis=1)
    v_plane = radius_m * omega_s[:, None] * np.stack([np.zeros_like(s), c, s], axis=1)
    a_plane = radius_m * (
        alpha_s[:, None] * np.stack([np.zeros_like(s), c, s], axis=1)
        + (omega_s**2)[:, None] * np.stack([np.zeros_like(s), -s, c], axis=1)
    )
    pos = p_plane @ R_plane.T
    vel = v_plane @ R_plane.T
    acc = a_plane @ R_plane.T

    g_world = np.array([0.0, 0.0, -g], dtype=np.float64)
    quats = np.zeros((n, 4), dtype=np.float64)
    gyro = np.zeros((n, 3), dtype=np.float64)
    accel = np.zeros((n, 3), dtype=np.float64)

    for i in range(n):
        radial = pos[i] / (np.linalg.norm(pos[i]) + 1e-12)
        z_axis = radial
        x_axis = normal_world
        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis) + 1e-12
        x_axis = np.cross(y_axis, z_axis)
        x_axis /= np.linalg.norm(x_axis) + 1e-12
        R = np.stack([x_axis, y_axis, z_axis], axis=1)
        q = so3.rotmat_to_quat(R)
        if i > 0:
            q = so3.ensure_quat_hemisphere(q, quats[i - 1])
        quats[i] = q
        gyro[i] = R.T @ (omega_s[i] * normal_world)
        accel[i] = R.T @ (acc[i] - g_world)

    # Broadband strike transient: damped high-frequency ring at impact
    if impact_shock_g > 0:
        tau = t - t[impact_idx]
        ring = np.where(
            tau >= 0.0,
            np.exp(-tau / max(shock_decay_s, 1e-4)) * np.sin(2 * np.pi * shock_ring_hz * tau),
            0.0,
        )
        direction = np.array([0.0, 1.0, 0.3], dtype=np.float64)
        direction /= np.linalg.norm(direction)
        shock_world = impact_shock_g * g * ring[:, None] * direction[None, :]
        for i in range(n):
            accel[i] += so3.quat_to_rotmat(quats[i]).T @ shock_world[i]

    phases = SwingPhases(
        address_idx=int(address_idx),
        top_idx=int(top_idx),
        impact_idx=int(impact_idx),
        finish_idx=int(finish_idx),
    )
    phases.validate_order()

    peak_idx = top_idx + int(np.argmax(np.abs(omega_s[top_idx : impact_idx + 1])))
    packet = ImuPacket(
        frame=SensorFrame(fs_hz=fs_hz, wrist=WristSide.LEAD), t=t, gyro=gyro, accel=accel
    )
    return SyntheticSwing(
        packet=packet,
        phases_true=phases,
        quats_true=quats,
        positions_true=pos,
        velocities_true=vel,
        angles=theta,
        omega_scalar=omega_s,
        alpha_scalar=alpha_s,
        peak_omega_time_s=float(t[peak_idx]),
        impact_time_s=float(t[impact_idx]),
        casting=casting,
        meta={
            "radius_m": radius_m,
            "plane_tilt_deg": plane_tilt_deg,
            "peak_omega_rad_s": float(np.max(np.abs(omega_s))),
            "peak_to_impact_s": float(t[impact_idx] - t[peak_idx]),
            "a1": a1,
            "a2": a2,
        },
    )
