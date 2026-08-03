"""Event-anchored phase normalization for multi-channel swing waveforms.

Hard anchors: Address → Top → Impact → Finish. Each interval is resampled onto a
fixed grid independently so Impact never drifts across a boundary. Optional
narrow-band DTW within a phase is deferred; linear event warping is the default
(Lauer / SciRep-style event alignment without unconstrained DTW erasure).

Actual phase durations are retained separately so tempo remains first-class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]


@dataclass
class PhaseNormalizedSwing:
    """Fixed-grid multi-channel waveform with retained real durations."""

    grids: dict[str, ArrayF]  # phase_name -> (n_grid, n_channels)
    channel_names: tuple[str, ...]
    phase_durations_s: dict[str, float]
    phase_grid_sizes: dict[str, int]
    warp_cost: float  # 0 for linear; reserved for future constrained DTW
    validity: bool
    meta: dict[str, float] = field(default_factory=dict)


_DEFAULT_GRID = {
    "address_to_top": 48,
    "top_to_impact": 32,
    "impact_to_finish": 32,
}


def _resample_segment(x: ArrayF, n_out: int) -> ArrayF:
    """Linear resample rows of ``x`` (T, C) onto ``n_out`` samples."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    t_in = x.shape[0]
    if t_in < 2 or n_out < 2:
        return np.repeat(x[:1], n_out, axis=0)
    src = np.linspace(0.0, 1.0, t_in)
    dst = np.linspace(0.0, 1.0, n_out)
    out = np.zeros((n_out, x.shape[1]), dtype=np.float64)
    for c in range(x.shape[1]):
        out[:, c] = np.interp(dst, src, x[:, c])
    return out


def phase_normalize(
    t: ArrayLike,
    channels: ArrayLike,
    phases: SwingPhases,
    *,
    channel_names: tuple[str, ...] | None = None,
    grid_sizes: dict[str, int] | None = None,
) -> PhaseNormalizedSwing:
    """Resample channels onto event-anchored fixed grids."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    x = np.asarray(channels, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    n = t.shape[0]
    if x.shape[0] != n:
        raise ValueError("channels length must match t")
    names = channel_names or tuple(f"ch{i}" for i in range(x.shape[1]))
    if len(names) != x.shape[1]:
        raise ValueError("channel_names length mismatch")
    gridspec = dict(_DEFAULT_GRID)
    if grid_sizes:
        gridspec.update(grid_sizes)

    a, top, imp, fin = (
        int(np.clip(phases.address_idx, 0, n - 1)),
        int(np.clip(phases.top_idx, 0, n - 1)),
        int(np.clip(phases.impact_idx, 0, n - 1)),
        int(np.clip(phases.finish_idx, 0, n - 1)),
    )
    valid = a < top < imp < fin
    segments = {
        "address_to_top": (a, top),
        "top_to_impact": (top, imp),
        "impact_to_finish": (imp, fin),
    }
    out_grids: dict[str, ArrayF] = {}
    durations: dict[str, float] = {}
    for name, (lo, hi) in segments.items():
        hi = max(hi, lo + 1)
        seg = x[lo : hi + 1]
        durations[name] = float(t[hi] - t[lo])
        out_grids[name] = _resample_segment(seg, int(gridspec[name]))

    return PhaseNormalizedSwing(
        grids=out_grids,
        channel_names=names,
        phase_durations_s=durations,
        phase_grid_sizes={k: int(v) for k, v in gridspec.items()},
        warp_cost=0.0,
        validity=bool(valid),
        meta={
            "address_idx": float(a),
            "top_idx": float(top),
            "impact_idx": float(imp),
            "finish_idx": float(fin),
            "n_channels": float(x.shape[1]),
        },
    )


def concatenate_phases(normed: PhaseNormalizedSwing) -> ArrayF:
    """Stack phase grids into one (T_total, C) matrix for PCA / distance."""
    parts = [
        normed.grids["address_to_top"],
        normed.grids["top_to_impact"],
        normed.grids["impact_to_finish"],
    ]
    return np.vstack(parts)
