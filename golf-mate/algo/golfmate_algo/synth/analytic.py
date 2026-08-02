"""Analytic / synthetic IMU generators with known ground truth."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.math import so3
from golfmate_algo.types import ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]


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
    g: float = 9.80665,
) -> AnalyticRotationTruth:
    """IMU undergoing pure constant-rate rotation about ``axis``.

    Accelerometer reports specific force of a rotating body with origin fixed
    (no linear accel): a_body = -R^T g_world.
    """
    n = int(round(duration_s * fs_hz))
    dt = 1.0 / fs_hz
    t = np.arange(n, dtype=np.float64) * dt
    axis_v = np.asarray(axis, dtype=np.float64)
    axis_v = axis_v / (np.linalg.norm(axis_v) + 1e-12)
    omega = axis_v * rate_rad_s

    quats = np.zeros((n, 4), dtype=np.float64)
    gyro = np.zeros((n, 3), dtype=np.float64)
    accel = np.zeros((n, 3), dtype=np.float64)
    q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    for i in range(n):
        quats[i] = q
        gyro[i] = omega
        R = so3.quat_to_rotmat(q)
        accel[i] = -R.T @ (np.array([0.0, 0.0, -g]))
        q = so3.integrate_gyro_rk4(q, omega, dt)

    frame = SensorFrame(fs_hz=fs_hz, wrist=WristSide.LEAD)
    packet = ImuPacket(frame=frame, t=t, gyro=gyro, accel=accel)
    return AnalyticRotationTruth(
        packet=packet, quats_true=quats, omega_axis=axis_v, omega_rate=rate_rad_s
    )


@dataclass
class SyntheticSwing:
    packet: ImuPacket
    phases_true: SwingPhases
    quats_true: ArrayF
    positions_true: ArrayF
    casting: bool


def planar_circular_swing(
    fs_hz: float = 200.0,
    radius_m: float = 0.45,
    *,
    backswing_s: float = 0.75,
    downswing_s: float = 0.25,
    finish_s: float = 0.40,
    address_s: float = 0.30,
    impact_spike_g: float = 8.0,
    casting: bool = False,
    g: float = 9.80665,
) -> SyntheticSwing:
    """Generate a planar circular wrist path with known phases.

    Motion in world YZ plane (normal ≈ X): address at bottom, top at far back,
    impact at bottom with accel spike, finish forward.
    """
    dt = 1.0 / fs_hz
    n_addr = int(round(address_s * fs_hz))
    n_bs = int(round(backswing_s * fs_hz))
    n_ds = int(round(downswing_s * fs_hz))
    n_fin = int(round(finish_s * fs_hz))
    n = n_addr + n_bs + n_ds + n_fin
    t = np.arange(n, dtype=np.float64) * dt

    # Angle schedule: 0 at address bottom, +θ at top, back to 0 at impact, -φ at finish
    theta_top = np.deg2rad(110.0)
    theta_fin = np.deg2rad(-40.0)

    angles = np.zeros(n, dtype=np.float64)
    # address hold
    angles[:n_addr] = 0.0
    # backswing: 0 → theta_top (smoothstep)
    u = np.linspace(0.0, 1.0, n_bs, endpoint=False)
    angles[n_addr : n_addr + n_bs] = theta_top * (u * u * (3 - 2 * u))
    # downswing: theta_top → 0
    u = np.linspace(0.0, 1.0, n_ds, endpoint=False)
    # casting: front-load angular progress so peak |ω| arrives early before impact
    if casting:
        w = 1.0 - np.power(1.0 - u, 4.0)  # very fast early, flat near end
    else:
        # smoothstep with late peak ω near impact (ease-in)
        w = np.power(u, 2.5)
    angles[n_addr + n_bs : n_addr + n_bs + n_ds] = theta_top * (1.0 - w)
    # finish: 0 → theta_fin
    u = np.linspace(0.0, 1.0, n_fin)
    angles[n_addr + n_bs + n_ds :] = theta_fin * (u * u * (3 - 2 * u))

    # Position on circle in YZ, center at origin, address at (0,0,-r)
    pos = np.zeros((n, 3), dtype=np.float64)
    pos[:, 1] = radius_m * np.sin(angles)
    pos[:, 2] = -radius_m * np.cos(angles)

    # Numerical velocity / acceleration in world
    vel = np.gradient(pos, dt, axis=0)
    acc_world = np.gradient(vel, dt, axis=0)

    # Orientation: body x along plane normal (world X), body z roughly radial outward
    quats = np.zeros((n, 4), dtype=np.float64)
    gyro = np.zeros((n, 3), dtype=np.float64)
    accel = np.zeros((n, 3), dtype=np.float64)

    omega_world = np.zeros((n, 3), dtype=np.float64)
    omega_world[:, 0] = np.gradient(angles, dt)  # rotation about +X

    for i in range(n):
        # Build R: x-axis = plane normal, z = radial from center to wrist, y = z×x
        radial = pos[i] / (np.linalg.norm(pos[i]) + 1e-12)
        x_axis = np.array([1.0, 0.0, 0.0])
        z_axis = radial
        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis) + 1e-12
        x_axis = np.cross(y_axis, z_axis)
        x_axis /= np.linalg.norm(x_axis) + 1e-12
        R = np.stack([x_axis, y_axis, z_axis], axis=1)
        q = so3.rotmat_to_quat(R)
        if i > 0:
            q = so3.ensure_quat_hemisphere(q, quats[i - 1])
        quats[i] = q
        # body gyro = R^T ω_world
        gyro[i] = R.T @ omega_world[i]
        # specific force: a_lin_world - g_world, in body: R^T (acc_world - g_world)
        # wait: lin_acc_world = acc_world; specific force in world = acc_world - g_world
        # a_meas_body = R^T * (acc_world - g_world)
        g_world = np.array([0.0, 0.0, -g])
        accel[i] = R.T @ (acc_world[i] - g_world)

    # Impact spike on accel magnitude at impact index (distinct from centripetal)
    impact_idx = n_addr + n_bs + n_ds - 1
    R_imp = so3.quat_to_rotmat(quats[impact_idx])
    spike = R_imp.T @ np.array([impact_spike_g * g * 3.0, 0.0, 0.0])
    accel[impact_idx] = accel[impact_idx] + spike
    if impact_idx > 0:
        accel[impact_idx - 1] = accel[impact_idx - 1] + 0.35 * spike
    if impact_idx + 1 < n:
        accel[impact_idx + 1] = accel[impact_idx + 1] + 0.25 * spike

    address_idx = n_addr - 1
    top_idx = n_addr + n_bs - 1
    finish_idx = n - 1
    phases = SwingPhases(
        address_idx=address_idx,
        top_idx=top_idx,
        impact_idx=impact_idx,
        finish_idx=finish_idx,
    )
    phases.validate_order()

    frame = SensorFrame(fs_hz=fs_hz, wrist=WristSide.LEAD)
    packet = ImuPacket(frame=frame, t=t, gyro=gyro, accel=accel)
    return SyntheticSwing(
        packet=packet,
        phases_true=phases,
        quats_true=quats,
        positions_true=pos,
        casting=casting,
    )
