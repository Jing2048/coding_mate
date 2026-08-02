"""SO(3) utilities: quaternions [w,x,y,z] and 6D rotation representations."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]


def as_quat(q: ArrayLike) -> ArrayF:
    q = np.asarray(q, dtype=np.float64).reshape(4)
    return q


def normalize_quat(q: ArrayLike, eps: float = 1e-12) -> ArrayF:
    q = as_quat(q)
    n = np.linalg.norm(q)
    if n < eps:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    return q / n


def quat_conjugate(q: ArrayLike) -> ArrayF:
    q = as_quat(q)
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def quat_multiply(q1: ArrayLike, q2: ArrayLike) -> ArrayF:
    """Hamilton product q1 ⊗ q2."""
    w1, x1, y1, z1 = as_quat(q1)
    w2, x2, y2, z2 = as_quat(q2)
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=np.float64,
    )


def quat_to_rotmat(q: ArrayLike) -> ArrayF:
    """Body → world rotation matrix for quaternion q (rotates body vectors to world)."""
    w, x, y, z = normalize_quat(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def rotmat_to_quat(R: ArrayLike) -> ArrayF:
    """Shepperd's method; returns unit quaternion [w,x,y,z]."""
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)
    t = np.trace(R)
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return normalize_quat([w, x, y, z])


def rotate_vector(q: ArrayLike, v: ArrayLike) -> ArrayF:
    """Rotate vector v from body to world using q."""
    R = quat_to_rotmat(q)
    return R @ np.asarray(v, dtype=np.float64).reshape(3)


def quat_from_axis_angle(axis: ArrayLike, angle_rad: float) -> ArrayF:
    axis = np.asarray(axis, dtype=np.float64).reshape(3)
    n = np.linalg.norm(axis)
    if n < 1e-12 or abs(angle_rad) < 1e-16:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    axis = axis / n
    half = 0.5 * angle_rad
    s = np.sin(half)
    return np.array([np.cos(half), *(axis * s)], dtype=np.float64)


def integrate_gyro_rk4(q: ArrayLike, omega_body: ArrayLike, dt: float) -> ArrayF:
    """Right-invariant strapdown: dq/dt = 0.5 * q ⊗ [0, ω].

    Exact closed form for constant ω over dt (Rodrigues on SO(3) via quaternion).
    """
    q = normalize_quat(q)
    omega = np.asarray(omega_body, dtype=np.float64).reshape(3)
    angle = np.linalg.norm(omega) * dt
    dq = quat_from_axis_angle(omega, angle) if angle > 0 else np.array(
        [1.0, 0.0, 0.0, 0.0], dtype=np.float64
    )
    # For constant ω: q_new = q ⊗ quat(ω*dt)
    return normalize_quat(quat_multiply(q, dq))


def geodesic_distance(q1: ArrayLike, q2: ArrayLike) -> float:
    """Angle (rad) between orientations, accounting for double cover."""
    q1 = normalize_quat(q1)
    q2 = normalize_quat(q2)
    dot = float(np.clip(abs(np.dot(q1, q2)), 0.0, 1.0))
    return 2.0 * float(np.arccos(dot))


def ensure_quat_hemisphere(q: ArrayLike, ref: ArrayLike) -> ArrayF:
    q = as_quat(q)
    ref = as_quat(ref)
    if np.dot(q, ref) < 0:
        q = -q
    return normalize_quat(q)


def rotmat_to_6d(R: ArrayLike) -> ArrayF:
    """Zhou et al. CVPR 2019: first two columns of rotation matrix."""
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)
    return np.concatenate([R[:, 0], R[:, 1]]).astype(np.float64)


def quat_to_6d(q: ArrayLike) -> ArrayF:
    return rotmat_to_6d(quat_to_rotmat(q))


def rotmat_from_6d(r6: ArrayLike) -> ArrayF:
    """Gram-Schmidt orthonormalization of 6D representation."""
    r6 = np.asarray(r6, dtype=np.float64).reshape(6)
    a1 = r6[:3]
    a2 = r6[3:]
    b1 = a1 / (np.linalg.norm(a1) + 1e-12)
    a2_proj = a2 - np.dot(b1, a2) * b1
    b2 = a2_proj / (np.linalg.norm(a2_proj) + 1e-12)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=1)


def quat_from_6d(r6: ArrayLike) -> ArrayF:
    return rotmat_to_quat(rotmat_from_6d(r6))


def quat_from_two_vectors(a: ArrayLike, b: ArrayLike) -> ArrayF:
    """Shortest rotation taking unit vector a to unit vector b."""
    a = np.asarray(a, dtype=np.float64).reshape(3)
    b = np.asarray(b, dtype=np.float64).reshape(3)
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    c = np.cross(a, b)
    d = float(np.dot(a, b))
    if d < -0.999999:
        # 180 deg: pick orthogonal axis
        axis = np.array([1.0, 0.0, 0.0])
        if abs(a[0]) > 0.9:
            axis = np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, axis)
        axis = axis / (np.linalg.norm(axis) + 1e-12)
        return quat_from_axis_angle(axis, np.pi)
    q = np.array([1.0 + d, *c], dtype=np.float64)
    return normalize_quat(q)


G_WORLD = np.array([0.0, 0.0, -9.80665], dtype=np.float64)
