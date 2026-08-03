"""Axis mirroring for handedness / wrist-side → canonical lead-right frame."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.types import Handedness, WristSide

ArrayF = NDArray[np.float64]

# Lateral (Y) reflection: left-handed lead wrist → right-handed lead anatomy.
_M_LEFT = np.diag([1.0, -1.0, 1.0]).astype(np.float64)

# Trail wrist → lead anatomy: 180° about the distal (X) axis, then same lateral
# sense as lead. Composed as diag(-1, -1, 1) so det = +1 (proper rotation).
_M_TRAIL = np.diag([-1.0, -1.0, 1.0]).astype(np.float64)


def mirror_matrix(
    handedness: Handedness,
    wrist: WristSide,
) -> ArrayF:
    """Return the 3×3 map from device-anatomy vectors → canonical lead-right."""
    m = np.eye(3, dtype=np.float64)
    if handedness == Handedness.LEFT:
        m = _M_LEFT @ m
    if wrist == WristSide.TRAIL:
        m = _M_TRAIL @ m
    return m


def apply_linear_map(vectors: ArrayF, matrix: ArrayF) -> ArrayF:
    """Apply ``matrix @ v`` to each row of ``vectors`` (N,3)."""
    return (matrix @ np.asarray(vectors, dtype=np.float64).T).T


def needs_mirror(handedness: Handedness, wrist: WristSide) -> bool:
    return handedness != Handedness.RIGHT or wrist != WristSide.LEAD
