"""Kinematic sequence proxy for single-wrist P0 (degraded observability).

Cheetham-style proximal→distal sequencing needs multi-segment angular velocity.
With one distal node we only observe wrist |ω| peak timing vs impact, plus an
optional plane-rate vs twist-rate lag proxy when segment channels are supplied.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.types import SwingPhases


@dataclass
class SequenceProxy:
    """Single-node proxy: only wrist ω peak timing is fully observable."""

    wrist_peak_idx: int
    wrist_peak_to_impact_s: float
    plane_peak_to_impact_s: float = float("nan")
    twist_peak_to_impact_s: float = float("nan")
    lag_proxy_s: float = float("nan")  # twist_peak − plane_peak (positive = twist later)
    note: str = (
        "Full pelvis→torso→arm→club sequence requires multi-IMU or learned mapping (P1)."
    )


def sequence_proxy(
    t: ArrayLike,
    gyro: ArrayLike,
    phases: SwingPhases,
    *,
    plane_rate: ArrayLike | None = None,
    twist_rate: ArrayLike | None = None,
) -> SequenceProxy:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    omega = np.linalg.norm(np.asarray(gyro, dtype=np.float64).reshape(-1, 3), axis=1)
    lo, hi = phases.top_idx, phases.impact_idx
    rel = int(np.argmax(omega[lo : hi + 1]))
    idx = lo + rel
    plane_to_imp = float("nan")
    twist_to_imp = float("nan")
    lag = float("nan")
    if plane_rate is not None and twist_rate is not None and hi > lo:
        pr = np.asarray(plane_rate, dtype=np.float64).reshape(-1)
        tr = np.asarray(twist_rate, dtype=np.float64).reshape(-1)
        i_pl = lo + int(np.argmax(pr[lo : hi + 1]))
        i_tw = lo + int(np.argmax(np.abs(tr[lo : hi + 1])))
        plane_to_imp = float(t[phases.impact_idx] - t[i_pl])
        twist_to_imp = float(t[phases.impact_idx] - t[i_tw])
        lag = float(t[i_tw] - t[i_pl])
    return SequenceProxy(
        wrist_peak_idx=idx,
        wrist_peak_to_impact_s=float(t[phases.impact_idx] - t[idx]),
        plane_peak_to_impact_s=plane_to_imp,
        twist_peak_to_impact_s=twist_to_imp,
        lag_proxy_s=lag,
    )
