"""Ideal kinematic template bands from healthy multibody swings.

Bands are percentile envelopes (P25–P75), not a single 'correct posture'.
Product copy must keep ``is_proxy=True`` and never claim absolute form truth.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from golfmate_algo.synth.multibody import SwingConfig, build_swing

_TEMPLATE_PATH = Path(__file__).with_name("ideal_template.json")

FEATURE_KEYS: tuple[str, ...] = (
    "tempo_s",
    "rhythm",
    "peak_omega_to_impact_s",
    "plane_angle_deg",
    "hand_speed_peak_m_s",
    "sequence_score_proxy",
)


@dataclass(frozen=True)
class IdealBand:
    name: str
    p25: float
    p50: float
    p75: float


@dataclass(frozen=True)
class IdealTemplate:
    version: str
    n_train: int
    bands: dict[str, IdealBand]
    notes: str = (
        "Percentile bands from healthy multibody swings; not a unique ideal pose."
    )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "n_train": self.n_train,
            "notes": self.notes,
            "bands": {k: asdict(v) for k, v in self.bands.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> IdealTemplate:
        bands = {
            k: IdealBand(name=k, p25=float(v["p25"]), p50=float(v["p50"]), p75=float(v["p75"]))
            for k, v in d["bands"].items()
        }
        return cls(version=str(d["version"]), n_train=int(d["n_train"]), bands=bands, notes=d.get("notes", ""))


def _feature_row_from_report(report) -> dict[str, float]:
    f = report.features
    return {
        "tempo_s": float(f.tempo_s),
        "rhythm": float(f.rhythm),
        "peak_omega_to_impact_s": float(f.peak_omega_to_impact_s),
        "plane_angle_deg": float(f.plane_angle_deg),
        "hand_speed_peak_m_s": float(f.hand_speed_peak_m_s),
        "sequence_score_proxy": float(f.extras.get("sequence_score_proxy", 0.5)),
    }


def fit_ideal_template(
    n_swings: int = 24,
    seed: int = 0,
    *,
    write: bool = True,
) -> IdealTemplate:
    """Fit percentile bands on healthy (non-casting) multibody swings."""
    # Lazy import avoids circular dependency with pipeline → reference.score.
    from golfmate_algo.pipeline import analyze_swing

    rng = np.random.default_rng(seed)
    rows: dict[str, list[float]] = {k: [] for k in FEATURE_KEYS}
    for i in range(n_swings):
        cfg = SwingConfig(
            fs_hz=200.0,
            plane_tilt_deg=float(rng.choice([45.0, 55.0, 65.0])),
            backswing_s=float(rng.uniform(0.70, 0.90)),
            downswing_s=float(rng.uniform(0.22, 0.30)),
        )
        truth = build_swing(cfg)
        # Disable compare_to_ideal to avoid load→fit recursion while fitting.
        report = analyze_swing(
            truth.to_imu_packet(), use_crop_lite=False, compare_to_ideal=False
        )
        feat = _feature_row_from_report(report)
        for k in FEATURE_KEYS:
            rows[k].append(feat[k])

    bands: dict[str, IdealBand] = {}
    for k, vals in rows.items():
        arr = np.asarray(vals, dtype=np.float64)
        bands[k] = IdealBand(
            name=k,
            p25=float(np.percentile(arr, 25)),
            p50=float(np.percentile(arr, 50)),
            p75=float(np.percentile(arr, 75)),
        )
    tmpl = IdealTemplate(version="ideal-v1", n_train=n_swings, bands=bands)
    if write:
        _TEMPLATE_PATH.write_text(json.dumps(tmpl.to_dict(), indent=2), encoding="utf-8")
    return tmpl


_FALLBACK_BANDS = {
    "tempo_s": IdealBand("tempo_s", 0.95, 1.05, 1.20),
    "rhythm": IdealBand("rhythm", 2.5, 3.0, 3.6),
    "peak_omega_to_impact_s": IdealBand("peak_omega_to_impact_s", -0.02, 0.02, 0.06),
    "plane_angle_deg": IdealBand("plane_angle_deg", 45.0, 55.0, 65.0),
    "hand_speed_peak_m_s": IdealBand("hand_speed_peak_m_s", 3.0, 5.0, 8.0),
    "sequence_score_proxy": IdealBand("sequence_score_proxy", 0.55, 0.75, 0.95),
}


def load_ideal_template() -> IdealTemplate:
    if _TEMPLATE_PATH.exists():
        return IdealTemplate.from_dict(json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8")))
    # Never auto-fit here (would recurse through analyze_swing).
    return IdealTemplate(version="ideal-v1-fallback", n_train=0, bands=_FALLBACK_BANDS)
