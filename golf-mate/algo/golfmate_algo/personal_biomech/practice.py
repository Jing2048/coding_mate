"""Practice-loop-v1 features from personal scores + optional session history."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from golfmate_algo.personal_biomech.cues import PracticeCue, cue_for_metric
from golfmate_algo.personal_biomech.prior import (
    CORE_PRIOR_METRICS,
    PersonalScore,
    score_against_prior,
    PersonalBiomechPrior,
)
from golfmate_algo.quality.uncertainty import (
    MetricEstimate,
    MetricKind,
    Validity,
    clip_confidence,
)

PRACTICE_LOOP_VERSION = "practice-loop-v1"
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "practice-loop-v1.json"

# Prefer timing/tempo KPIs when z-scores tie.
_FOCUS_PRIORITY: tuple[str, ...] = (
    "tempo_s",
    "rhythm",
    "peak_omega_to_impact_s",
    "peak_omega_rad_s",
    "plane_angle_deg",
    "hand_speed_peak_m_s",
    "trajectory_radius_m",
)


@dataclass
class PracticeLoopFeatures:
    """practice-loop-v1 next-shot correction features."""

    version: str = PRACTICE_LOOP_VERSION
    implemented: bool = True
    focus_metric: str | None = None
    in_window: bool | None = None
    error_sign: float | None = None
    correction_direction: float | None = None
    suggested_cue: str | None = None
    session_consistency: float | None = None
    reasons: list[str] = field(default_factory=list)
    metrics: list[MetricEstimate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "implemented": bool(self.implemented),
            "focus_metric": self.focus_metric,
            "focus_kpi": self.focus_metric,  # alias for commercial section field
            "in_window": self.in_window,
            "error_sign": _finite_or_none(self.error_sign),
            "correction_direction": _finite_or_none(self.correction_direction),
            "suggested_cue": self.suggested_cue,
            "session_consistency": _finite_or_none(self.session_consistency),
            "reasons": list(self.reasons),
            "metrics": [m.as_dict() for m in self.metrics],
            "meta": dict(self.meta),
        }


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _sign(x: float) -> float:
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


def select_focus_metric(
    score: PersonalScore,
    *,
    explicit: str | None = None,
    min_confidence: float = 0.35,
) -> tuple[str | None, list[str]]:
    """Pick focus metric: explicit if reliable, else worst reliable |z|."""
    reasons: list[str] = []
    if explicit:
        s = score.scores.get(explicit)
        if (
            s is not None
            and s.validity in (Validity.OK, Validity.DEGRADED)
            and math.isfinite(s.z_score)
            and s.confidence >= min_confidence
            and s.baseline in ("personal", "tour")
        ):
            reasons.append("explicit_focus")
            return explicit, reasons
        reasons.append("explicit_focus_unreliable")

    candidates: list[tuple[float, int, str]] = []
    priority = {n: i for i, n in enumerate(_FOCUS_PRIORITY)}
    for name, s in score.scores.items():
        if name not in CORE_PRIOR_METRICS and name not in _FOCUS_PRIORITY:
            continue
        if s.validity not in (Validity.OK, Validity.DEGRADED):
            continue
        if not math.isfinite(s.z_score) or s.confidence < min_confidence:
            continue
        if s.baseline == "none":
            continue
        # Prefer personal over tour when ranking ties on |z|.
        personal_boost = 0.05 if s.baseline == "personal" else 0.0
        candidates.append((-(abs(s.z_score) + personal_boost), priority.get(name, 99), name))

    if not candidates:
        reasons.append("no_reliable_focus_metric")
        return None, reasons

    candidates.sort()
    chosen = candidates[0][2]
    reasons.append("auto_worst_reliable_z")
    return chosen, reasons


def _session_consistency(
    session_scores: Sequence[PersonalScore] | None,
    focus: str | None,
) -> tuple[float | None, list[str]]:
    if not session_scores or not focus:
        return None, ["session_consistency_abstain"]
    flags: list[bool] = []
    for ps in session_scores:
        s = ps.scores.get(focus)
        if s is None or s.in_window is None or s.validity == Validity.ABSTAIN:
            continue
        flags.append(bool(s.in_window))
    if len(flags) < 2:
        return None, ["session_consistency_insufficient"]
    return float(sum(1 for f in flags if f) / len(flags)), ["session_consistency_from_in_window"]


def build_practice_loop_features(
    report: Any,
    prior: PersonalBiomechPrior | None,
    *,
    focus_metric: str | None = None,
    session_scores: Sequence[PersonalScore] | None = None,
    personal_score: PersonalScore | None = None,
) -> PracticeLoopFeatures:
    """Build practice-loop-v1 features. Abstains cleanly without a usable score."""
    score = personal_score or score_against_prior(report, prior)
    reasons: list[str] = []

    if prior is None:
        # Tour fallback still allowed via score_against_prior; mark soft reason.
        reasons.append("no_personal_prior_tour_fallback_possible")

    focus, focus_reasons = select_focus_metric(score, explicit=focus_metric)
    reasons.extend(focus_reasons)

    in_window: bool | None = None
    error_sign: float | None = None
    correction_direction: float | None = None
    suggested: PracticeCue = PracticeCue.ABSTAIN
    metric_list: list[MetricEstimate] = []

    if focus is None:
        reasons.append("practice_loop_abstain")
        # Still emit labeled abstain metrics for contract stability.
        for name in CORE_PRIOR_METRICS:
            s = score.scores.get(name)
            if s is not None:
                metric_list.append(s.as_metric_estimate())
        return PracticeLoopFeatures(
            version=PRACTICE_LOOP_VERSION,
            implemented=True,
            focus_metric=None,
            in_window=None,
            error_sign=None,
            correction_direction=None,
            suggested_cue=PracticeCue.ABSTAIN.value,
            session_consistency=None,
            reasons=reasons,
            metrics=metric_list,
            meta={"status": "abstain"},
        )

    s = score.scores[focus]
    in_window = s.in_window
    if math.isfinite(s.signed_error):
        error_sign = _sign(s.signed_error)
        # Correction pushes toward baseline (opposite of error).
        correction_direction = -error_sign if error_sign != 0.0 else 0.0
    suggested = cue_for_metric(
        focus, signed_error=s.signed_error if math.isfinite(s.signed_error) else None,
        in_window=in_window,
    )
    reasons.append(f"cue={suggested.value}")

    consistency, cons_reasons = _session_consistency(session_scores, focus)
    reasons.extend(cons_reasons)

    # Metric-labeled outputs for the focus + supporting personal deltas.
    metric_list.append(
        MetricEstimate(
            name="focus_z",
            value=float(s.z_score) if math.isfinite(s.z_score) else float("nan"),
            units="1",
            kind=MetricKind.DERIVED,
            confidence=s.confidence,
            validity=s.validity,
            residual=abs(s.z_score) if math.isfinite(s.z_score) else float("nan"),
            reasons=[f"focus={focus}", *list(s.reasons)],
            extras={
                "focus_metric": focus,
                "error_sign": error_sign,
                "correction_direction": correction_direction,
                "in_window": in_window,
                "baseline": s.baseline,
            },
        )
    )
    metric_list.append(s.as_metric_estimate())
    if consistency is not None:
        metric_list.append(
            MetricEstimate(
                name="session_consistency",
                value=float(consistency),
                units="1",
                kind=MetricKind.DERIVED,
                confidence=clip_confidence(0.55 + 0.3 * float(consistency)),
                validity=Validity.OK,
                residual=1.0 - float(consistency),
                reasons=cons_reasons,
                extras={"focus_metric": focus},
            )
        )

    return PracticeLoopFeatures(
        version=PRACTICE_LOOP_VERSION,
        implemented=True,
        focus_metric=focus,
        in_window=in_window,
        error_sign=error_sign,
        correction_direction=correction_direction,
        suggested_cue=suggested.value,
        session_consistency=consistency,
        reasons=reasons,
        metrics=metric_list,
        meta={
            "status": "ok",
            "baseline": s.baseline,
            "suggested_cue_enum": suggested.value,
        },
    )


def load_practice_loop_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


__all__ = [
    "PRACTICE_LOOP_VERSION",
    "PracticeLoopFeatures",
    "build_practice_loop_features",
    "load_practice_loop_schema",
    "select_focus_metric",
]
