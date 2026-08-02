"""Kinematic sequence proxy for single-wrist P0 (degraded observability)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.types import SwingPhases


@dataclass
class SequenceProxy:
    """Single-node proxy: only wrist ω peak timing is observable."""

    wrist_peak_idx: int
    wrist_peak_to_impact_s: float
    note: str = (
        "Full pelvis→torso→arm→club sequence requires multi-IMU or learned mapping (P1)."
    )


def sequence_proxy(
    t: ArrayLike, gyro: ArrayLike, phases: SwingPhases
) -> SequenceProxy:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    omega = np.linalg.norm(np.asarray(gyro, dtype=np.float64).reshape(-1, 3), axis=1)
    lo, hi = phases.top_idx, phases.impact_idx
    rel = int(np.argmax(omega[lo : hi + 1]))
    idx = lo + rel
    return SequenceProxy(
        wrist_peak_idx=idx,
        wrist_peak_to_impact_s=float(t[phases.impact_idx] - t[idx]),
    )
