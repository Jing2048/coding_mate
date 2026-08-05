"""Strategy-v1 precursor features — not strokes gained.

Derived from a swing sequence plus optional contexts. Missing context abstains
fields rather than inventing values.

When ``SwingContext.club_id`` is present, pressure / miss / consistency /
biomechanics-z dispersion are computed **within club** then robustly
aggregated. Driver pressure is never compared to 7i calm.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from golfmate_algo.personal_biomech.context import SwingContext
from golfmate_algo.personal_biomech.prior import (
    CORE_PRIOR_METRICS,
    PersonalBiomechPrior,
    PersonalScore,
    extract_core_metrics,
    score_against_prior,
)
from golfmate_algo.quality.uncertainty import (
    MetricEstimate,
    MetricKind,
    Validity,
    clip_confidence,
)

STRATEGY_VERSION = "strategy-v1"
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "strategy-v1.json"
_BAD_STREAK_Z = 2.0
_ALL_COHORT = "all"
# Biomechanics z-dispersion (personal |z| MAD) — not ball / shot dispersion.
DISPERSION_METRIC_NAME = "biomech_z_dispersion"
DISPERSION_KIND = "biomechanics_z_dispersion"


@dataclass
class StrategyFeatures:
    """strategy-v1 round/practice precursor features (explicitly not SG)."""

    version: str = STRATEGY_VERSION
    implemented: bool = True
    tempo_under_pressure: float | None = None
    dispersion: float | None = None
    miss_bias: float | None = None
    consistency_decay: float | None = None
    bad_streak: int | None = None
    reasons: list[str] = field(default_factory=list)
    metrics: list[MetricEstimate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "implemented": bool(self.implemented),
            "tempo_under_pressure": _finite_or_none(self.tempo_under_pressure),
            "dispersion": _finite_or_none(self.dispersion),
            "miss_bias": _finite_or_none(self.miss_bias),
            "consistency_decay": _finite_or_none(self.consistency_decay),
            "bad_streak": self.bad_streak,
            "reasons": list(self.reasons),
            "metrics": [m.as_dict() for m in self.metrics],
            "meta": dict(self.meta),
        }


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _median(vals: Sequence[float]) -> float:
    xs = sorted(float(v) for v in vals if math.isfinite(v))
    if not xs:
        return float("nan")
    mid = len(xs) // 2
    if len(xs) % 2:
        return float(xs[mid])
    return 0.5 * (xs[mid - 1] + xs[mid])


def _mad(vals: Sequence[float], center: float) -> float:
    return _median([abs(float(v) - center) for v in vals])


def _club_key(ctx: SwingContext | None) -> str | None:
    """Return club_id when present; None means unknown (no stratification id)."""
    if ctx is None:
        return None
    cid = ctx.club_id
    if cid is None:
        return None
    text = str(cid).strip()
    return text if text else None


def _mean_abs_z(ps: PersonalScore) -> float | None:
    zs = [
        abs(float(s.z_score))
        for s in ps.scores.values()
        if s.validity != Validity.ABSTAIN
        and math.isfinite(s.z_score)
        and s.baseline != "none"
        and s.name in CORE_PRIOR_METRICS
    ]
    if not zs:
        return None
    return float(sum(zs) / len(zs))


def _biomech_z_abs(ps: PersonalScore) -> list[float]:
    out: list[float] = []
    for name in CORE_PRIOR_METRICS:
        s = ps.scores.get(name)
        if (
            s is None
            or s.validity == Validity.ABSTAIN
            or not math.isfinite(s.z_score)
            or s.baseline == "none"
        ):
            continue
        out.append(abs(float(s.z_score)))
    return out


def _cohort_tempo_delta(
    pressure_tempos: Sequence[float],
    calm_tempos: Sequence[float],
) -> float | None:
    if not pressure_tempos or not calm_tempos:
        return None
    return float(_median(pressure_tempos) - _median(calm_tempos))


def _cohort_dispersion(z_abs: Sequence[float]) -> float | None:
    if len(z_abs) < 3:
        return None
    med = _median(z_abs)
    return float(1.4826 * _mad(z_abs, med))


def _cohort_consistency_decay(per_swing_z: Sequence[float]) -> float | None:
    if len(per_swing_z) < 4:
        return None
    mid = len(per_swing_z) // 2
    early = _median(per_swing_z[:mid])
    late = _median(per_swing_z[mid:])
    return float(late - early)


def _cohort_bad_streak(per_swing_z: Sequence[float]) -> int | None:
    if not per_swing_z:
        return None
    streak = 0
    for z in reversed(list(per_swing_z)):
        if z >= _BAD_STREAK_Z:
            streak += 1
        else:
            break
    return int(streak)


def build_strategy_features(
    reports: Sequence[Any],
    contexts: Sequence[SwingContext | None] | None = None,
    *,
    prior: PersonalBiomechPrior | None = None,
    personal_scores: Sequence[PersonalScore] | None = None,
) -> StrategyFeatures:
    """Build strategy-v1 features from a sequence + optional contexts.

    Explicitly **not** strokes gained. Club-stratified when club_id exists:
    pressure tempo compares pressure vs calm **within the same club**, then
    robustly aggregates valid club deltas. Miss bias / consistency /
    biomechanics-z dispersion expose by-club summaries in meta.
    """
    reasons: list[str] = [
        "not_strokes_gained",
        "strategy_v1_precursor",
        "dispersion_is_biomech_z_not_ball",
    ]
    n = len(reports)
    ctxs: list[SwingContext | None]
    if contexts is None:
        ctxs = [None] * n
        reasons.append("contexts_missing")
    else:
        ctxs = list(contexts)
        if len(ctxs) != n:
            raise ValueError("contexts length must match reports length")

    scores = list(personal_scores) if personal_scores is not None else [
        score_against_prior(r, prior) for r in reports
    ]

    has_any_club = any(_club_key(c) is not None for c in ctxs)
    club_context_missing = not has_any_club
    if club_context_missing:
        reasons.append("club_context_missing")

    # --- per-club / all cohort buckets ---
    # tempo: club -> {"pressure": [...], "calm": [...]}
    tempo_by_club: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"pressure": [], "calm": []}
    )
    miss_by_club: dict[str, list[float]] = defaultdict(list)
    z_abs_by_club: dict[str, list[float]] = defaultdict(list)
    mean_z_by_club: dict[str, list[float]] = defaultdict(list)
    # Preserve swing order within each club for consistency_decay / bad_streak.
    ordered_mean_z_by_club: dict[str, list[float]] = defaultdict(list)

    for report, ctx, ps in zip(reports, ctxs, scores):
        club = _club_key(ctx) if has_any_club else _ALL_COHORT
        if has_any_club and club is None:
            # Swings without club_id when others have one: skip stratified pools
            # (do not mix into a foreign club).
            reasons.append("swing_missing_club_id_skipped")
            continue
        assert club is not None

        metrics = extract_core_metrics(report)
        tempo = metrics.get("tempo_s")
        if (
            tempo is not None
            and tempo.validity != Validity.ABSTAIN
            and math.isfinite(tempo.value)
            and ctx is not None
            and ctx.pressure is not None
        ):
            bucket = "pressure" if ctx.pressure else "calm"
            tempo_by_club[club][bucket].append(float(tempo.value))

        if (
            ctx is not None
            and ctx.has_miss_context
            and ctx.miss_direction is not None
            and math.isfinite(float(ctx.miss_direction))
        ):
            miss_by_club[club].append(float(ctx.miss_direction))

        z_abs = _biomech_z_abs(ps)
        z_abs_by_club[club].extend(z_abs)
        mz = _mean_abs_z(ps)
        if mz is not None:
            mean_z_by_club[club].append(mz)
            ordered_mean_z_by_club[club].append(mz)

    # --- tempo under pressure: within-club then aggregate ---
    tempo_by_club_summary: dict[str, Any] = {}
    club_tempo_deltas: list[float] = []
    clubs_for_tempo = sorted(tempo_by_club.keys())
    if club_context_missing and _ALL_COHORT not in clubs_for_tempo:
        clubs_for_tempo = [_ALL_COHORT]
        tempo_by_club[_ALL_COHORT] = {"pressure": [], "calm": []}
    for club in clubs_for_tempo:
        buckets = tempo_by_club[club]
        delta = _cohort_tempo_delta(buckets["pressure"], buckets["calm"])
        entry: dict[str, Any] = {
            "n_pressure": len(buckets["pressure"]),
            "n_calm": len(buckets["calm"]),
            "delta": _finite_or_none(delta),
            "valid": delta is not None,
        }
        if club == _ALL_COHORT and club_context_missing:
            entry["reason"] = "club_context_missing"
        tempo_by_club_summary[club] = entry
        if delta is not None:
            club_tempo_deltas.append(delta)

    tempo_under_pressure: float | None = None
    tempo_validity = Validity.ABSTAIN
    if club_tempo_deltas:
        tempo_under_pressure = float(_median(club_tempo_deltas))
        if club_context_missing:
            tempo_validity = Validity.DEGRADED
            reasons.append("tempo_under_pressure_all_cohort_degraded")
        else:
            tempo_validity = Validity.OK
            reasons.append("tempo_under_pressure_club_stratified")
    else:
        reasons.append("tempo_under_pressure_abstain")

    # --- biomechanics z-dispersion (not ball dispersion) ---
    disp_by_club_summary: dict[str, Any] = {}
    club_dispersions: list[float] = []
    for club, z_abs in sorted(z_abs_by_club.items()):
        d = _cohort_dispersion(z_abs)
        entry = {
            "n_z": len(z_abs),
            "dispersion": _finite_or_none(d),
            "valid": d is not None,
            "kind": DISPERSION_KIND,
        }
        if club == _ALL_COHORT and club_context_missing:
            entry["reason"] = "club_context_missing"
        disp_by_club_summary[club] = entry
        if d is not None:
            club_dispersions.append(d)

    dispersion: float | None = None
    disp_validity = Validity.ABSTAIN
    if club_dispersions:
        dispersion = float(_median(club_dispersions))
        if club_context_missing:
            disp_validity = Validity.DEGRADED
            reasons.append("biomech_z_dispersion_all_cohort_degraded")
        else:
            disp_validity = Validity.OK
            reasons.append("biomech_z_dispersion_club_stratified")
    else:
        reasons.append("dispersion_abstain")

    # --- miss_bias: per-club then aggregate ---
    miss_by_club_summary: dict[str, Any] = {}
    club_miss: list[float] = []
    for club, vals in sorted(miss_by_club.items()):
        if not vals:
            continue
        med = float(_median(vals))
        entry = {
            "n": len(vals),
            "miss_bias": med,
            "valid": True,
        }
        if club == _ALL_COHORT and club_context_missing:
            entry["reason"] = "club_context_missing"
        miss_by_club_summary[club] = entry
        club_miss.append(med)

    miss_bias: float | None = None
    miss_validity = Validity.ABSTAIN
    if club_miss:
        miss_bias = float(_median(club_miss))
        if club_context_missing:
            miss_validity = Validity.DEGRADED
            reasons.append("miss_bias_all_cohort_degraded")
        else:
            miss_validity = Validity.OK
            reasons.append("miss_bias_club_stratified")
    else:
        reasons.append("miss_bias_abstain_missing_context")

    # --- consistency_decay + bad_streak: per-club then aggregate ---
    cons_by_club_summary: dict[str, Any] = {}
    club_decays: list[float] = []
    club_streaks: list[int] = []
    for club, series in sorted(ordered_mean_z_by_club.items()):
        decay = _cohort_consistency_decay(series)
        streak = _cohort_bad_streak(series)
        entry: dict[str, Any] = {
            "n": len(series),
            "consistency_decay": _finite_or_none(decay),
            "bad_streak": streak,
            "valid_decay": decay is not None,
            "valid_streak": streak is not None,
        }
        if club == _ALL_COHORT and club_context_missing:
            entry["reason"] = "club_context_missing"
        cons_by_club_summary[club] = entry
        if decay is not None:
            club_decays.append(decay)
        if streak is not None:
            club_streaks.append(streak)

    consistency_decay: float | None = None
    cons_validity = Validity.ABSTAIN
    if club_decays:
        consistency_decay = float(_median(club_decays))
        if club_context_missing:
            cons_validity = Validity.DEGRADED
            reasons.append("consistency_decay_all_cohort_degraded")
        else:
            cons_validity = Validity.OK
            reasons.append("consistency_decay_club_stratified")
    else:
        reasons.append("consistency_decay_abstain")

    bad_streak: int | None = None
    streak_validity = Validity.ABSTAIN
    if club_streaks:
        # Robust aggregate: median streak across valid club cohorts.
        bad_streak = int(round(_median([float(s) for s in club_streaks])))
        if club_context_missing:
            streak_validity = Validity.DEGRADED
            reasons.append("bad_streak_all_cohort_degraded")
        else:
            streak_validity = Validity.OK
            reasons.append("bad_streak_club_stratified")
    else:
        reasons.append("bad_streak_abstain")

    # Deduplicate reasons while preserving order.
    deduped: list[str] = []
    seen_reasons: set[str] = set()
    for r in reasons:
        if r not in seen_reasons:
            seen_reasons.add(r)
            deduped.append(r)
    reasons = deduped

    metrics: list[MetricEstimate] = []

    def _add(
        name: str,
        value: float | None,
        *,
        units: str,
        validity: Validity,
        reasons_local: list[str],
        residual: float = float("nan"),
        extras: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> None:
        if value is None or not math.isfinite(value) or validity == Validity.ABSTAIN:
            metrics.append(
                MetricEstimate(
                    name=name,
                    value=float("nan"),
                    units=units,
                    kind=MetricKind.DERIVED,
                    confidence=0.1,
                    validity=Validity.ABSTAIN,
                    residual=float("nan"),
                    reasons=reasons_local,
                    extras=dict(extras or {}),
                )
            )
        else:
            conf = confidence
            if conf is None:
                conf = 0.45 if validity == Validity.DEGRADED else 0.55
            metrics.append(
                MetricEstimate(
                    name=name,
                    value=float(value),
                    units=units,
                    kind=MetricKind.DERIVED,
                    confidence=clip_confidence(conf),
                    validity=validity,
                    residual=residual if math.isfinite(residual) else float("nan"),
                    reasons=reasons_local,
                    extras=dict(extras or {}),
                )
            )

    tempo_reasons = (
        ["pressure_vs_calm_tempo_delta_within_club"]
        if tempo_under_pressure is not None and not club_context_missing
        else (
            ["pressure_vs_calm_tempo_delta", "club_context_missing"]
            if tempo_under_pressure is not None
            else ["tempo_under_pressure_abstain"]
        )
    )
    _add(
        "tempo_under_pressure",
        tempo_under_pressure,
        units="s",
        validity=tempo_validity,
        reasons_local=tempo_reasons,
        residual=abs(tempo_under_pressure) if tempo_under_pressure is not None else float("nan"),
        extras={"by_club": tempo_by_club_summary},
    )

    disp_reasons = (
        ["biomech_z_dispersion_mad_of_abs_z", "not_ball_dispersion"]
        if dispersion is not None
        else ["dispersion_abstain"]
    )
    if club_context_missing and dispersion is not None:
        disp_reasons.append("club_context_missing")
    _add(
        DISPERSION_METRIC_NAME,
        dispersion,
        units="1",
        validity=disp_validity,
        reasons_local=disp_reasons,
        residual=float(dispersion) if dispersion is not None else float("nan"),
        extras={
            "field": "dispersion",
            "kind": DISPERSION_KIND,
            "by_club": disp_by_club_summary,
            "not_ball_dispersion": True,
        },
    )
    # Keep legacy field-name alias metric for commercial section consumers.
    if dispersion is not None:
        metrics.append(
            MetricEstimate(
                name="dispersion",
                value=float(dispersion),
                units="1",
                kind=MetricKind.DERIVED,
                confidence=clip_confidence(0.45 if disp_validity == Validity.DEGRADED else 0.55),
                validity=disp_validity,
                residual=float(dispersion),
                reasons=disp_reasons + ["alias_of_biomech_z_dispersion"],
                extras={
                    "canonical_name": DISPERSION_METRIC_NAME,
                    "kind": DISPERSION_KIND,
                    "not_ball_dispersion": True,
                },
            )
        )
    else:
        metrics.append(
            MetricEstimate(
                name="dispersion",
                value=float("nan"),
                units="1",
                kind=MetricKind.DERIVED,
                confidence=0.1,
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                reasons=["dispersion_abstain", "alias_of_biomech_z_dispersion"],
                extras={
                    "canonical_name": DISPERSION_METRIC_NAME,
                    "kind": DISPERSION_KIND,
                    "not_ball_dispersion": True,
                },
            )
        )

    miss_reasons = (
        ["miss_direction_median_within_club"]
        if miss_bias is not None and not club_context_missing
        else (
            ["miss_direction_median", "club_context_missing"]
            if miss_bias is not None
            else ["miss_bias_abstain_missing_context"]
        )
    )
    _add(
        "miss_bias",
        miss_bias,
        units="1",
        validity=miss_validity,
        reasons_local=miss_reasons,
        residual=abs(miss_bias) if miss_bias is not None else float("nan"),
        extras={"by_club": miss_by_club_summary},
    )

    cons_reasons = (
        ["late_minus_early_mean_abs_z_within_club"]
        if consistency_decay is not None and not club_context_missing
        else (
            ["late_minus_early_mean_abs_z", "club_context_missing"]
            if consistency_decay is not None
            else ["consistency_decay_abstain"]
        )
    )
    _add(
        "consistency_decay",
        consistency_decay,
        units="1",
        validity=cons_validity,
        reasons_local=cons_reasons,
        residual=abs(consistency_decay) if consistency_decay is not None else float("nan"),
        extras={"by_club": cons_by_club_summary},
    )

    if bad_streak is None or streak_validity == Validity.ABSTAIN:
        metrics.append(
            MetricEstimate(
                name="bad_streak",
                value=float("nan"),
                units="1",
                kind=MetricKind.DERIVED,
                confidence=0.1,
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                reasons=["bad_streak_abstain"],
                extras={"by_club": cons_by_club_summary},
            )
        )
    else:
        metrics.append(
            MetricEstimate(
                name="bad_streak",
                value=float(bad_streak),
                units="1",
                kind=MetricKind.DERIVED,
                confidence=clip_confidence(
                    0.45 if streak_validity == Validity.DEGRADED else 0.6
                ),
                validity=streak_validity,
                residual=float(bad_streak),
                reasons=(
                    ["bad_streak_from_mean_abs_z", "club_context_missing"]
                    if club_context_missing
                    else ["bad_streak_from_mean_abs_z_within_club"]
                ),
                extras={"by_club": cons_by_club_summary},
            )
        )

    implemented = n > 0
    return StrategyFeatures(
        version=STRATEGY_VERSION,
        implemented=implemented,
        tempo_under_pressure=tempo_under_pressure,
        dispersion=dispersion,
        miss_bias=miss_bias,
        consistency_decay=consistency_decay,
        bad_streak=bad_streak,
        reasons=reasons,
        metrics=metrics,
        meta={
            "n_swings": n,
            "not_strokes_gained": True,
            "status": "ok" if implemented else "abstain",
            "club_context_missing": club_context_missing,
            "club_stratified": has_any_club,
            "dispersion_kind": DISPERSION_KIND,
            "dispersion_canonical_name": DISPERSION_METRIC_NAME,
            "by_club": {
                "tempo_under_pressure": tempo_by_club_summary,
                "biomech_z_dispersion": disp_by_club_summary,
                "miss_bias": miss_by_club_summary,
                "consistency": cons_by_club_summary,
            },
        },
    )


def load_strategy_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


__all__ = [
    "DISPERSION_KIND",
    "DISPERSION_METRIC_NAME",
    "STRATEGY_VERSION",
    "StrategyFeatures",
    "build_strategy_features",
    "load_strategy_schema",
]
