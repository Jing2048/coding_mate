"""Swing plane estimation via SVD and planar circle fit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]


@dataclass
class SwingPlaneResult:
    normal: ArrayF  # (3,)
    centroid: ArrayF  # (3,)
    radius: float
    center_3d: ArrayF  # (3,)
    plane_residual_rms: float
    circle_residual_rms: float
    plane_angle_deg: float  # angle between plane normal and world vertical


def fit_swing_plane(positions: ArrayLike, mask: ArrayLike | None = None) -> SwingPlaneResult:
    pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    if mask is not None:
        m = np.asarray(mask, dtype=bool).reshape(-1)
        pos = pos[m]
    if pos.shape[0] < 3:
        raise ValueError("need >= 3 points")

    c = pos.mean(axis=0)
    x = pos - c
    _, _, vh = np.linalg.svd(x, full_matrices=False)
    normal = vh[-1]
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    # Orient normal so z component >= 0 for stability
    if normal[2] < 0:
        normal = -normal

    plane_res = x @ normal
    plane_rms = float(np.sqrt(np.mean(plane_res**2)))

    # Orthonormal basis in plane
    ref = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(normal, ref)
    e1 /= np.linalg.norm(e1) + 1e-12
    e2 = np.cross(normal, e1)
    e2 /= np.linalg.norm(e2) + 1e-12
    pts2 = np.column_stack([x @ e1, x @ e2])

    center2, radius = _fit_circle_2d(pts2)
    center_3d = c + center2[0] * e1 + center2[1] * e2
    circ_res = np.linalg.norm(pts2 - center2, axis=1) - radius
    circ_rms = float(np.sqrt(np.mean(circ_res**2)))

    vertical = np.array([0.0, 0.0, 1.0])
    # plane angle: angle between plane and horizontal = angle between normal and vertical
    cosang = float(np.clip(abs(np.dot(normal, vertical)), 0.0, 1.0))
    plane_angle_deg = float(np.degrees(np.arccos(cosang)))

    return SwingPlaneResult(
        normal=normal.astype(np.float64),
        centroid=c.astype(np.float64),
        radius=float(radius),
        center_3d=center_3d.astype(np.float64),
        plane_residual_rms=plane_rms,
        circle_residual_rms=circ_rms,
        plane_angle_deg=plane_angle_deg,
    )


def _fit_circle_2d(pts: ArrayF) -> tuple[ArrayF, float]:
    """Algebraic circle fit (Kåsa)."""
    x = pts[:, 0]
    y = pts[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    b = x**2 + y**2
    sol, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    r = float(np.sqrt(max(c + cx**2 + cy**2, 0.0)))
    return np.array([cx, cy], dtype=np.float64), r
