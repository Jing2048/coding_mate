"""CommercialSwingReport v2 — strict metric semantics + downstream feature contracts.

Truth / inference metrics are populated from an existing ``SwingReport``.
Personal baseline, practice-loop, and strategy sections are stable serializable
placeholders (``implemented=False``); the personal engine is not wired yet.

Does not mutate ``SwingReport`` — export-only layer for commercial consumers.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from golfmate_algo.quality.uncertainty import (
    REQUIRED_METRIC_KEYS,
    MetricEstimate,
    MetricKind,
    Validity,
    clip_confidence,
    trajectory_validity,
    validate_metric_dict,
)
from golfmate_algo.types import DiagnosticFinding, SwingReport

CONTRACT_VERSION = "commercial-swing-report-v2"
PRACTICE_LOOP_VERSION = "practice-loop-v1"
STRATEGY_VERSION = "strategy-v1"
PERSONAL_BASELINE_VERSION = "personal-baseline-v1"

_SCHEMA_PATH = Path(__file__).with_name("commercial_report_schema.json")

# Stable P0 truth metric names (citeable wrist / timing layer).
TRUTH_METRIC_NAMES: tuple[str, ...] = (
    "tempo_s",
    "backswing_s",
    "downswing_s",
    "rhythm",
    "peak_omega_rad_s",
    "peak_omega_to_impact_s",
    "hand_speed_peak_m_s",
    "plane_angle_deg",
    "trajectory_radius_m",
)

# Stable inference / proxy metric names (never claim measured).
INFERENCE_METRIC_NAMES: tuple[str, ...] = (
    "wrist_fe_impact_deg",
    "wrist_fe_delta_address_to_impact_deg",
    "wrist_ru_impact_deg",
    "clubface_impact_deg",
    "shaft_lean_impact_deg",
    "x_factor_top_deg",
    "x_factor_proxy_deg",
    "sequence_score_proxy",
    "casting_onset_s",
    "segment_twist_rate_proxy_rad_s",
    "high_order_residual",
)

PRACTICE_LOOP_FIELD_NAMES: tuple[str, ...] = (
    "focus_kpi",
    "in_window",
    "correction_direction",
    "session_consistency",
)

STRATEGY_FIELD_NAMES: tuple[str, ...] = (
    "tempo_under_pressure",
    "dispersion",
    "miss_bias",
    "consistency_decay",
)


def _finding_as_dict(f: DiagnosticFinding) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key, value in f.evidence.items():
        try:
            out = float(value)
            evidence[key] = out if math.isfinite(out) else None
        except (TypeError, ValueError):
            evidence[key] = value if isinstance(value, (str, bool)) else None
    return {
        "code": f.code,
        "severity": f.severity,
        "message": f.message,
        "evidence": evidence,
        "is_proxy": bool(f.is_proxy),
        "kind": str(getattr(f, "kind", "proxy") or "proxy"),
    }


@dataclass
class PersonalBaselineSection:
    """Relative-to-self signed errors — placeholder until personal engine ships."""

    version: str = PERSONAL_BASELINE_VERSION
    implemented: bool = False
    deltas: list[MetricEstimate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "implemented": self.implemented,
            "deltas": [m.as_dict() for m in self.deltas],
            "meta": dict(self.meta),
        }


@dataclass
class PracticeLoopSection:
    """practice-loop-v1 feature contract (schema frozen; engine not implemented)."""

    version: str = PRACTICE_LOOP_VERSION
    implemented: bool = False
    focus_kpi: str | None = None
    in_window: bool | None = None
    correction_direction: float | None = None
    session_consistency: float | None = None
    metrics: list[MetricEstimate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "implemented": self.implemented,
            "focus_kpi": self.focus_kpi,
            "in_window": self.in_window,
            "correction_direction": self.correction_direction,
            "session_consistency": self.session_consistency,
            "metrics": [m.as_dict() for m in self.metrics],
            "meta": dict(self.meta),
        }


@dataclass
class StrategySection:
    """strategy-v1 feature contract (schema frozen; engine not implemented)."""

    version: str = STRATEGY_VERSION
    implemented: bool = False
    tempo_under_pressure: float | None = None
    dispersion: float | None = None
    miss_bias: float | None = None
    consistency_decay: float | None = None
    metrics: list[MetricEstimate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "implemented": self.implemented,
            "tempo_under_pressure": self.tempo_under_pressure,
            "dispersion": self.dispersion,
            "miss_bias": self.miss_bias,
            "consistency_decay": self.consistency_decay,
            "metrics": [m.as_dict() for m in self.metrics],
            "meta": dict(self.meta),
        }


@dataclass
class CommercialSwingReport:
    """Versioned commercial biomechanics report (v2).

    Sections:
      * truth — measured/derived citeable P0 wrist/timing metrics
      * inference — proxy + inferred high-order metrics
      * personal_baseline / practice_loop / strategy — stable placeholders
    """

    version: str
    truth: list[MetricEstimate]
    inference: list[MetricEstimate]
    personal_baseline: PersonalBaselineSection
    practice_loop: PracticeLoopSection
    strategy: StrategySection
    findings: list[DiagnosticFinding] = field(default_factory=list)
    phases: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "truth": [m.as_dict() for m in self.truth],
            "inference": [m.as_dict() for m in self.inference],
            "personal_baseline": self.personal_baseline.as_dict(),
            "practice_loop": self.practice_loop.as_dict(),
            "strategy": self.strategy.as_dict(),
            "findings": [_finding_as_dict(f) for f in self.findings],
            "phases": dict(self.phases),
            "meta": dict(self.meta),
        }

    def all_metrics(self) -> list[MetricEstimate]:
        out = list(self.truth) + list(self.inference)
        out.extend(self.personal_baseline.deltas)
        out.extend(self.practice_loop.metrics)
        out.extend(self.strategy.metrics)
        return out


def _metric(
    name: str,
    value: float,
    units: str,
    kind: MetricKind,
    confidence: float,
    validity: Validity,
    *,
    residual: float = float("nan"),
    reasons: list[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> MetricEstimate:
    return MetricEstimate(
        name=name,
        value=float(value),
        units=units,
        kind=kind,
        confidence=clip_confidence(float(confidence)),
        validity=validity,
        residual=float(residual),
        reasons=list(reasons or []),
        extras=dict(extras or {}),
    )


def _meta_float(meta: dict[str, Any], key: str, default: float = float("nan")) -> float:
    val = meta.get(key, default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def _radius_from_report(meta: dict[str, Any]) -> float:
    if "radius_m" in meta:
        return _meta_float(meta, "radius_m")
    pro = meta.get("pro_swing")
    if isinstance(pro, dict):
        for m in pro.get("metrics") or []:
            if isinstance(m, dict) and m.get("name") == "trajectory_radius_m":
                try:
                    return float(m.get("value", float("nan")))
                except (TypeError, ValueError):
                    return float("nan")
    return float("nan")


def _build_truth_metrics(report: SwingReport) -> list[MetricEstimate]:
    f = report.features
    meta = report.meta if isinstance(report.meta, dict) else {}
    radius = _radius_from_report(meta)
    residual_rms = _meta_float(meta, "residual_rms_m_s2", 0.0)
    rank = _meta_float(meta, "rank", 3.0)
    fallback = _meta_float(meta, "fallback", 0.0)
    traj_v, traj_reasons, traj_conf = trajectory_validity(
        radius_m=radius if math.isfinite(radius) else 0.0,
        residual_rms=residual_rms,
        rank=rank,
        fallback=fallback,
    )

    plane_residual = _meta_float(meta, "plane_residual_rms", float("nan"))
    impact_mode = str(meta.get("impact_mode", "unknown"))
    timing_conf = 0.85
    timing_v = Validity.OK
    timing_reasons: list[str] = []
    if impact_mode in {"kinematic_proxy", "kinematic"}:
        timing_conf *= 0.8
        timing_reasons.append("impact_kinematic_proxy")
        timing_v = Validity.DEGRADED
    elif impact_mode in {"unavailable", "abstain"}:
        timing_conf *= 0.4
        timing_reasons.append("impact_unavailable")
        timing_v = Validity.ABSTAIN

    peak_conf = clip_confidence(0.9 if f.peak_omega_rad_s > 2.0 else 0.45)
    peak_v = Validity.OK if f.peak_omega_rad_s > 2.0 else Validity.DEGRADED

    return [
        _metric(
            "tempo_s",
            f.tempo_s,
            "s",
            MetricKind.DERIVED,
            timing_conf,
            timing_v,
            reasons=timing_reasons,
        ),
        _metric(
            "backswing_s",
            f.backswing_s,
            "s",
            MetricKind.DERIVED,
            timing_conf,
            timing_v,
            reasons=timing_reasons,
        ),
        _metric(
            "downswing_s",
            f.downswing_s,
            "s",
            MetricKind.DERIVED,
            timing_conf,
            timing_v,
            reasons=timing_reasons,
        ),
        _metric(
            "rhythm",
            f.rhythm,
            "1",
            MetricKind.DERIVED,
            timing_conf,
            timing_v,
            reasons=timing_reasons,
        ),
        _metric(
            "peak_omega_rad_s",
            f.peak_omega_rad_s,
            "rad/s",
            MetricKind.MEASURED,
            peak_conf,
            peak_v,
            reasons=[] if peak_v == Validity.OK else ["low_peak_omega"],
        ),
        _metric(
            "peak_omega_to_impact_s",
            f.peak_omega_to_impact_s,
            "s",
            MetricKind.DERIVED,
            timing_conf,
            timing_v,
            reasons=timing_reasons,
        ),
        _metric(
            "hand_speed_peak_m_s",
            f.hand_speed_peak_m_s,
            "m/s",
            MetricKind.DERIVED,
            traj_conf,
            traj_v,
            residual=residual_rms,
            reasons=traj_reasons,
        ),
        _metric(
            "plane_angle_deg",
            f.plane_angle_deg,
            "deg",
            MetricKind.DERIVED,
            clip_confidence(0.75 if (math.isfinite(plane_residual) and plane_residual < 0.08) else 0.45),
            Validity.OK
            if (math.isfinite(plane_residual) and plane_residual < 0.08)
            else Validity.DEGRADED,
            residual=plane_residual,
            reasons=[]
            if (math.isfinite(plane_residual) and plane_residual < 0.08)
            else ["plane_residual_high"],
        ),
        _metric(
            "trajectory_radius_m",
            float(radius),
            "m",
            MetricKind.DERIVED,
            traj_conf,
            traj_v,
            residual=residual_rms,
            reasons=traj_reasons,
        ),
    ]


def _build_inference_metrics(report: SwingReport) -> list[MetricEstimate]:
    meta = report.meta if isinstance(report.meta, dict) else {}
    high = meta.get("high_order") if isinstance(meta.get("high_order"), dict) else None
    proxies = meta.get("biomech_proxies") if isinstance(meta.get("biomech_proxies"), dict) else {}
    feats = report.features

    out: list[MetricEstimate] = []

    # Casting timing is a wrist-observable proxy (not clubface).
    casting_v = Validity.OK
    casting_conf = 0.7
    if abs(feats.peak_omega_to_impact_s) > 0.25:
        casting_v = Validity.DEGRADED
        casting_conf = 0.4
    out.append(
        _metric(
            "casting_onset_s",
            feats.peak_omega_to_impact_s,
            "s",
            MetricKind.PROXY,
            casting_conf,
            casting_v,
            reasons=["casting_timing_proxy"],
        )
    )
    out.append(
        _metric(
            "segment_twist_rate_proxy_rad_s",
            feats.closure_rate_rad_s,
            "rad/s",
            MetricKind.PROXY,
            0.65,
            Validity.DEGRADED,
            reasons=["segment_twist_not_clubface_closure"],
        )
    )

    px_conf = float(proxies.get("confidence", feats.extras.get("proxy_confidence", 0.3)))
    px_v = Validity.OK if px_conf >= 0.35 else Validity.DEGRADED
    out.append(
        _metric(
            "x_factor_proxy_deg",
            float(proxies.get("x_factor_proxy_deg", feats.extras.get("x_factor_proxy_deg", float("nan")))),
            "deg",
            MetricKind.PROXY,
            px_conf,
            px_v,
            reasons=["biomech_linear_proxy"],
        )
    )
    out.append(
        _metric(
            "sequence_score_proxy",
            float(proxies.get("sequence_score", feats.extras.get("sequence_score_proxy", float("nan")))),
            "1",
            MetricKind.PROXY,
            px_conf,
            px_v,
            reasons=["biomech_linear_proxy"],
        )
    )

    if high is None:
        # Explicit abstain slots so the inference section shape stays stable.
        for name, units in (
            ("wrist_fe_impact_deg", "deg"),
            ("wrist_fe_delta_address_to_impact_deg", "deg"),
            ("wrist_ru_impact_deg", "deg"),
            ("clubface_impact_deg", "deg"),
            ("shaft_lean_impact_deg", "deg"),
            ("x_factor_top_deg", "deg"),
            ("high_order_residual", "1"),
        ):
            out.append(
                _metric(
                    name,
                    float("nan"),
                    units,
                    MetricKind.INFERRED,
                    0.05,
                    Validity.ABSTAIN,
                    residual=float("nan"),
                    reasons=["high_order_unavailable"],
                )
            )
        return out

    conf = float(high.get("confidence", 0.3))
    residual = float(high.get("residual", float("nan")))
    try:
        validity = Validity(str(high.get("validity", "degraded")))
    except ValueError:
        validity = Validity.DEGRADED
    wrist = high.get("wrist") or {}
    club = high.get("club") or {}
    body = high.get("body") or {}
    reasons = ["high_order_pcr"]

    def _inf(name: str, value: float, units: str) -> MetricEstimate:
        return _metric(
            name,
            value,
            units,
            MetricKind.INFERRED,
            conf,
            validity,
            residual=residual,
            reasons=reasons,
            extras={"source": str(high.get("source", "high_order_pcr"))},
        )

    out.extend(
        [
            _inf("wrist_fe_impact_deg", float(wrist.get("fe_impact_deg", float("nan"))), "deg"),
            _inf(
                "wrist_fe_delta_address_to_impact_deg",
                float(wrist.get("fe_delta_address_to_impact_deg", float("nan"))),
                "deg",
            ),
            _inf("wrist_ru_impact_deg", float(wrist.get("ru_impact_deg", float("nan"))), "deg"),
            _inf("clubface_impact_deg", float(club.get("face_impact_deg", float("nan"))), "deg"),
            _inf(
                "shaft_lean_impact_deg",
                float(club.get("shaft_lean_impact_deg", float("nan"))),
                "deg",
            ),
            _inf("x_factor_top_deg", float(body.get("x_factor_top_deg", float("nan"))), "deg"),
            _metric(
                "high_order_residual",
                residual,
                "1",
                MetricKind.INFERRED,
                conf,
                validity,
                residual=residual,
                reasons=reasons,
            ),
        ]
    )
    return out


def build_commercial_report(report: SwingReport) -> CommercialSwingReport:
    """Project a backward-compatible ``SwingReport`` into CommercialSwingReport v2."""
    meta = report.meta if isinstance(report.meta, dict) else {}
    return CommercialSwingReport(
        version=CONTRACT_VERSION,
        truth=_build_truth_metrics(report),
        inference=_build_inference_metrics(report),
        personal_baseline=PersonalBaselineSection(
            meta={"note": "personal biomech prior not implemented in this release"},
        ),
        practice_loop=PracticeLoopSection(
            meta={
                "note": "practice-loop-v1 schema frozen; personal engine not wired",
                "fields": list(PRACTICE_LOOP_FIELD_NAMES),
            },
        ),
        strategy=StrategySection(
            meta={
                "note": "strategy-v1 schema frozen; personal engine not wired",
                "fields": list(STRATEGY_FIELD_NAMES),
            },
        ),
        findings=list(report.findings),
        phases=report.phases.as_dict(),
        meta={
            "source_backend": meta.get("backend"),
            "device_id": meta.get("device_id"),
            "impact_mode": meta.get("impact_mode"),
            "swing_report_compatible": True,
        },
    )


def export_commercial_report(report: SwingReport) -> dict[str, Any]:
    """Serialize CommercialSwingReport v2 as a JSON-ready dict."""
    return build_commercial_report(report).as_dict()


def validate_commercial_report_dict(d: dict[str, Any]) -> None:
    """Strict schema checks for a serialized commercial report."""
    if d.get("version") != CONTRACT_VERSION:
        raise ValueError(f"unexpected commercial report version: {d.get('version')!r}")
    for section in ("truth", "inference"):
        metrics = d.get(section)
        if not isinstance(metrics, list) or not metrics:
            raise ValueError(f"{section} must be a non-empty metric list")
        for m in metrics:
            validate_metric_dict(m)
    pb = d.get("personal_baseline") or {}
    if pb.get("version") != PERSONAL_BASELINE_VERSION:
        raise ValueError("personal_baseline.version mismatch")
    if pb.get("implemented") is not False:
        raise ValueError("personal_baseline.implemented must be False until engine ships")
    pl = d.get("practice_loop") or {}
    if pl.get("version") != PRACTICE_LOOP_VERSION:
        raise ValueError("practice_loop.version mismatch")
    if pl.get("implemented") is not False:
        raise ValueError("practice_loop.implemented must be False until engine ships")
    st = d.get("strategy") or {}
    if st.get("version") != STRATEGY_VERSION:
        raise ValueError("strategy.version mismatch")
    if st.get("implemented") is not False:
        raise ValueError("strategy.implemented must be False until engine ships")
    for f in d.get("findings") or []:
        if not isinstance(f, dict):
            raise ValueError("finding must be a dict")
        kind = f.get("kind", "proxy")
        if kind not in {m.value for m in MetricKind}:
            raise ValueError(f"invalid finding kind: {kind!r}")
        # Inferred high-order findings must never claim measured / is_proxy=False.
        if kind == MetricKind.INFERRED.value and f.get("is_proxy") is False:
            raise ValueError(f"inferred finding {f.get('code')} must keep is_proxy=True")


def load_commercial_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


__all__ = [
    "CONTRACT_VERSION",
    "INFERENCE_METRIC_NAMES",
    "PERSONAL_BASELINE_VERSION",
    "PRACTICE_LOOP_FIELD_NAMES",
    "PRACTICE_LOOP_VERSION",
    "REQUIRED_METRIC_KEYS",
    "STRATEGY_FIELD_NAMES",
    "STRATEGY_VERSION",
    "TRUTH_METRIC_NAMES",
    "CommercialSwingReport",
    "PersonalBaselineSection",
    "PracticeLoopSection",
    "StrategySection",
    "build_commercial_report",
    "export_commercial_report",
    "load_commercial_schema",
    "validate_commercial_report_dict",
]
