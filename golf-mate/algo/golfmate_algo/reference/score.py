"""Score a SwingReport against the ideal kinematic template bands."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from golfmate_algo.reference.ideal_kinematics import (
    FEATURE_KEYS,
    IdealTemplate,
    load_ideal_template,
)
from golfmate_algo.types import DiagnosticFinding, SwingReport


@dataclass(frozen=True)
class ReferenceScore:
    overall: float  # 0..1, higher = closer to healthy band
    per_feature: dict[str, float]
    confidence: float
    is_proxy: bool = True
    template_version: str = "ideal-v1"


def _band_score(value: float, p25: float, p75: float, p50: float) -> float:
    """1.0 inside [p25,p75]; decays with distance outside, scaled by band width."""
    width = max(p75 - p25, 1e-6)
    if p25 <= value <= p75:
        return 1.0
    dist = (p25 - value) if value < p25 else (value - p75)
    return float(np.clip(1.0 - dist / (2.0 * width), 0.0, 1.0))


def score_against_reference(
    report: SwingReport,
    template: IdealTemplate | None = None,
) -> ReferenceScore:
    tmpl = template or load_ideal_template()
    f = report.features
    values = {
        "tempo_s": float(f.tempo_s),
        "rhythm": float(f.rhythm),
        "peak_omega_to_impact_s": float(f.peak_omega_to_impact_s),
        "plane_angle_deg": float(f.plane_angle_deg),
        "hand_speed_peak_m_s": float(f.hand_speed_peak_m_s),
        "sequence_score_proxy": float(f.extras.get("sequence_score_proxy", 0.5)),
    }
    per: dict[str, float] = {}
    for k in FEATURE_KEYS:
        b = tmpl.bands[k]
        per[k] = _band_score(values[k], b.p25, b.p75, b.p50)
    overall = float(np.mean(list(per.values())))
    conf = float(np.clip(0.35 + 0.4 * overall, 0.1, 0.85))
    return ReferenceScore(
        overall=overall,
        per_feature=per,
        confidence=conf,
        is_proxy=True,
        template_version=tmpl.version,
    )


def reference_finding(score: ReferenceScore) -> DiagnosticFinding:
    """Proxy finding — never claims an absolute 'correct posture'."""
    if score.overall >= 0.85:
        msg = (
            "Kinematic proxies sit near the healthy synthetic reference band "
            "(not a unique ideal pose)."
        )
        sev = "info"
        code = "reference_near_band"
    elif score.overall >= 0.55:
        msg = (
            "Some kinematic proxies deviate from the healthy synthetic reference band "
            "(compare_to_ideal proxy)."
        )
        sev = "info"
        code = "reference_mild_deviation"
    else:
        msg = (
            "Kinematic proxies deviate substantially from the healthy synthetic "
            "reference band (compare_to_ideal proxy — not absolute form truth)."
        )
        sev = "warn"
        code = "reference_large_deviation"
    return DiagnosticFinding(
        code=code,
        severity=sev,
        message=msg,
        evidence={
            "reference_overall": score.overall,
            "reference_confidence": score.confidence,
            **{f"ref_{k}": v for k, v in score.per_feature.items()},
        },
        is_proxy=True,
    )
