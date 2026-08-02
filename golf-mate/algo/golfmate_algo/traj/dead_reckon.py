"""Dead-reckoning trajectory with event velocity constraints (ZUPT-like)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.ahrs.gated_vqf import gravity_remove
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]


def integrate_trap(y: ArrayF, dt: float) -> ArrayF:
    """Cumulative trapezoidal integral, starting at 0."""
    n = y.shape[0]
    out = np.zeros_like(y)
    if n < 2:
        return out
    for i in range(1, n):
        out[i] = out[i - 1] + 0.5 * (y[i] + y[i - 1]) * dt
    return out


def reconstruct_trajectory(
    quats: ArrayLike,
    accels: ArrayLike,
    dt: float,
    phases: SwingPhases | None = None,
    *,
    zupt_indices: list[int] | None = None,
) -> tuple[ArrayF, ArrayF, ArrayF]:
    """Return (lin_acc_world, velocity, position).

    If phases given, apply linear velocity drift removal so velocity ≈ 0 at
    Address, Top, and Finish (SciRep-style event constraints).
    """
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    accels = np.asarray(accels, dtype=np.float64).reshape(-1, 3)
    lin = gravity_remove(quats, accels)
    vel = integrate_trap(lin, dt)

    if phases is not None:
        zupt_indices = [
            phases.address_idx,
            phases.top_idx,
            phases.finish_idx,
        ]
    if zupt_indices:
        vel = _apply_piecewise_zupt(vel, sorted(set(int(i) for i in zupt_indices)))

    pos = integrate_trap(vel, dt)
    return lin, vel, pos


def _apply_piecewise_zupt(vel: ArrayF, idxs: list[int]) -> ArrayF:
    """Between consecutive ZUPT anchors, subtract linear velocity drift so
    endpoints are zeroed (and intermediate anchors met).
    """
    v = vel.copy()
    n = v.shape[0]
    anchors = [i for i in idxs if 0 <= i < n]
    if not anchors:
        return v
    # Force each anchor to zero by removing linear trend between anchors
    # First, zero the first anchor by subtracting its velocity from prefix
    a0 = anchors[0]
    v[: a0 + 1] -= v[a0]

    for a, b in zip(anchors[:-1], anchors[1:]):
        if b <= a:
            continue
        # After left zeroing, remove trend so v[b] → 0
        vb = v[b].copy()
        span = b - a
        for k in range(span + 1):
            alpha = k / span
            v[a + k] = v[a + k] - alpha * vb
        v[b] = 0.0

    # After last anchor: remove remaining constant bias using last anchor
    last = anchors[-1]
    if last < n - 1:
        # optionally leave free motion; subtract residual at last to keep continuity
        pass
    return v
