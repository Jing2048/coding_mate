"""Stable SwingFeatureVector export contract for future Core ML / on-device ML.

This round ships schema + Python exporter only — no ``.mlmodel``, no Swift.
Watch and glove clients should consume the same versioned float vector.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.types import SwingReport

CONTRACT_VERSION = "swing-features-v1"
_SCHEMA_PATH = Path(__file__).with_name("schema.json")

# Fixed order — do not reorder without bumping CONTRACT_VERSION.
FEATURE_NAMES: tuple[str, ...] = (
    "tempo_s",
    "backswing_s",
    "downswing_s",
    "rhythm",
    "peak_omega_rad_s",
    "peak_omega_to_impact_s",
    "hand_speed_peak_m_s",
    "plane_angle_deg",
    "closure_rate_rad_s",
    "x_factor_proxy_deg",
    "sequence_score_proxy",
    "proxy_confidence",
    "reference_overall",
    "reference_confidence",
    "impact_idx_norm",
    "top_idx_norm",
)


@dataclass(frozen=True)
class SwingFeatureVector:
    version: str
    names: tuple[str, ...]
    values: NDArray[np.float64]

    def as_dict(self) -> dict[str, float | str]:
        out: dict[str, float | str] = {"version": self.version}
        for n, v in zip(self.names, self.values, strict=True):
            out[n] = float(v)
        return out

    def as_array(self) -> NDArray[np.float64]:
        return np.asarray(self.values, dtype=np.float64)


def export_feature_vector(report: SwingReport) -> SwingFeatureVector:
    """Extract the versioned float vector from a SwingReport."""
    f = report.features
    n = max(int(report.quats.shape[0]), 1)
    ref = report.meta.get("reference_score", {}) if isinstance(report.meta, dict) else {}
    vals = [
        float(f.tempo_s),
        float(f.backswing_s),
        float(f.downswing_s),
        float(f.rhythm),
        float(f.peak_omega_rad_s),
        float(f.peak_omega_to_impact_s),
        float(f.hand_speed_peak_m_s),
        float(f.plane_angle_deg),
        float(f.closure_rate_rad_s),
        float(f.extras.get("x_factor_proxy_deg", 0.0)),
        float(f.extras.get("sequence_score_proxy", 0.5)),
        float(f.extras.get("proxy_confidence", 0.0)),
        float(ref.get("overall", 0.0)),
        float(ref.get("confidence", 0.0)),
        float(report.phases.impact_idx) / n,
        float(report.phases.top_idx) / n,
    ]
    return SwingFeatureVector(
        version=CONTRACT_VERSION,
        names=FEATURE_NAMES,
        values=np.asarray(vals, dtype=np.float64),
    )


def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
