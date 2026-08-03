"""Address-relative segment swing/twist channels (single rigid node).

A Watch or glove card observes ONE rigid segment. These channels are therefore
segment-orientation proxies — never true wrist joint angles (HackMotion needs
hand AND forearm). Naming follows ISB-inspired swing-twist decomposition.

References
----------
* Wu et al., ISB recommendations for upper-extremity joint coordinates, 2005.
* HackMotion calibration: address-relative segment angles.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]


@dataclass
class SegmentChannels:
    """Time series of address-relative segment channels (radians unless noted)."""

    twist_rad: ArrayF  # axial rotation about longitudinal / twist axis
    swing_rad: ArrayF  # remaining swing magnitude (geodesic minus twist)
    twist_rate_rad_s: ArrayF
    swing_rate_rad_s: ArrayF
    omega_plane_rad_s: ArrayF  # |ω| projected onto swing-plane tangent
    omega_twist_rad_s: ArrayF  # ω · twist_axis (body)
    twist_axis_body: ArrayF  # (3,) unit
    plane_normal_world: ArrayF  # (3,) unit estimate
    channel_kind: str  # "forearm_segment" | "hand_segment" | "unknown_segment"
    is_proxy: bool = True


def _twist_swing_decompose(q_rel: ArrayF, axis: ArrayF) -> tuple[ArrayF, ArrayF, float, float]:
    """Decompose relative quaternion into twist-about-axis + swing remainder."""
    q = so3.normalize_quat(q_rel)
    if q[0] < 0.0:
        q = -q
    v = q[1:]
    proj = float(np.dot(v, axis)) * axis
    q_twist = so3.normalize_quat(np.array([q[0], *proj], dtype=np.float64))
    q_swing = so3.normalize_quat(so3.quat_multiply(q, so3.quat_conjugate(q_twist)))
    twist = 2.0 * float(np.arctan2(np.linalg.norm(q_twist[1:]), q_twist[0]))
    # signed twist
    if float(np.dot(q_twist[1:], axis)) < 0.0:
        twist = -twist
    swing = 2.0 * float(np.arctan2(np.linalg.norm(q_swing[1:]), q_swing[0]))
    return q_twist, q_swing, twist, swing


def estimate_segment_channels(
    quats: ArrayLike,
    gyro: ArrayLike,
    dt: float,
    *,
    address_idx: int = 0,
    plane_normal_world: ArrayLike | None = None,
    channel_kind: str = "unknown_segment",
) -> SegmentChannels:
    """Build address-relative twist/swing channels from body→world quaternions.

    Twist axis defaults to the body +Z of the address pose (sensor longitudinal
    for a typical watch/glove mount after extrinsic calibration). Plane-normal
    projection uses an optional external estimate (e.g. from trajectory fit).
    """
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    n = quats.shape[0]
    addr = int(np.clip(address_idx, 0, n - 1))
    q0 = so3.normalize_quat(quats[addr])
    R0 = so3.quat_to_rotmat(q0)
    # Longitudinal sensor axis in body ≈ gravity-up at address projected...
    # Prefer body Z if mount is identity; fall back to gravity-aligned body up.
    twist_axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    up_b = -R0.T @ so3.G_WORLD
    up_b = up_b / (np.linalg.norm(up_b) + 1e-12)
    # If Z is nearly orthogonal to up, keep Z; else use up as twist for watch face
    if abs(float(np.dot(twist_axis, up_b))) < 0.3:
        twist_axis = up_b

    if plane_normal_world is None:
        # Fallback: world Y × gravity gives a rough target-line plane normal
        nrm = np.cross(np.array([0.0, 1.0, 0.0]), -so3.G_WORLD)
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
    else:
        nrm = np.asarray(plane_normal_world, dtype=np.float64).reshape(3)
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)

    twist = np.zeros(n, dtype=np.float64)
    swing = np.zeros(n, dtype=np.float64)
    om_plane = np.zeros(n, dtype=np.float64)
    om_twist = np.zeros(n, dtype=np.float64)
    for i in range(n):
        q_rel = so3.quat_multiply(so3.quat_conjugate(q0), so3.normalize_quat(quats[i]))
        _, _, tw, sw = _twist_swing_decompose(q_rel, twist_axis)
        twist[i] = tw
        swing[i] = sw
        # ω in body: project onto twist axis and onto plane (world→body)
        R = so3.quat_to_rotmat(quats[i])
        n_body = R.T @ nrm
        n_body = n_body / (np.linalg.norm(n_body) + 1e-12)
        om_twist[i] = float(np.dot(gyro[i], twist_axis))
        # Plane-tangent rate ≈ |ω × n|
        om_plane[i] = float(np.linalg.norm(np.cross(gyro[i], n_body)))

    # Unwrap twist for continuous rates
    twist = np.unwrap(twist)
    twist_rate = np.gradient(twist, dt)
    swing_rate = np.gradient(swing, dt)
    return SegmentChannels(
        twist_rad=twist,
        swing_rad=swing,
        twist_rate_rad_s=twist_rate,
        swing_rate_rad_s=swing_rate,
        omega_plane_rad_s=om_plane,
        omega_twist_rad_s=om_twist,
        twist_axis_body=twist_axis,
        plane_normal_world=nrm,
        channel_kind=channel_kind,
        is_proxy=True,
    )
