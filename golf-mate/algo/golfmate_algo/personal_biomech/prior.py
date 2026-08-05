"""Personal biomechanics prior — robust fit + signed scoring.

Uses only ok/degraded metrics (confidence-weighted). Robust center/scale via
median / MAD with per-metric floors. Abstains when min sample or coverage
gates fail. Personal baseline takes priority over tour/ideal bands.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from golfmate_algo.quality.uncertainty import (
    MetricEstimate,
    MetricKind,
    Validity,
    clip_confidence,
)
from golfmate_algo.reference.ideal_kinematics import load_ideal_template
from golfmate_algo.types import SwingReport

PERSONAL_BASELINE_VERSION = "personal-baseline-v1"

# Core citeable metrics for personal prior (no inferred face by default).
CORE_PRIOR_METRICS: tuple[str, ...] = (
    "tempo_s",
    "rhythm",
    "peak_omega_to_impact_s",
    "peak_omega_rad_s",
    "plane_angle_deg",
    "hand_speed_peak_m_s",
    "trajectory_radius_m",
)

# Face / clubface only when separately calibrated and usable.
OPTIONAL_FACE_METRICS: tuple[str, ...] = ("clubface_impact_deg",)

_METRIC_UNITS: dict[str, str] = {
    "tempo_s": "s",
    "rhythm": "1",
    "peak_omega_to_impact_s": "s",
    "peak_omega_rad_s": "rad/s",
    "plane_angle_deg": "deg",
    "hand_speed_peak_m_s": "m/s",
    "trajectory_radius_m": "m",
    "backswing_s": "s",
    "downswing_s": "s",
    "clubface_impact_deg": "deg",
}

# Absolute MAD floors — prevent zero-scale collapse on near-constant sessions.
_MAD_FLOORS: dict[str, float] = {
    "tempo_s": 0.02,
    "rhythm": 0.15,
    "peak_omega_to_impact_s": 0.005,
    "peak_omega_rad_s": 0.35,
    "plane_angle_deg": 1.5,
    "hand_speed_peak_m_s": 0.25,
    "trajectory_radius_m": 0.02,
    "backswing_s": 0.02,
    "downswing_s": 0.01,
    "clubface_impact_deg": 1.0,
}

_DEFAULT_MIN_SAMPLES = 5
_DEFAULT_MIN_COVERAGE = 0.4
_OUTLIER_Z = 4.0
_WINDOW_Z = 1.5
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "personal-baseline-v1.json"


@dataclass
class MetricPrior:
    """Robust personal baseline for one metric."""

    name: str
    center: float
    scale: float
    units: str
    kind: MetricKind
    n_samples: int
    coverage: float
    confidence: float
    validity: Validity
    window_lo: float
    window_hi: float
    mad_raw: float
    mad_floor: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "center": _finite_or_none(self.center),
            "scale": _finite_or_none(self.scale),
            "units": self.units,
            "kind": self.kind.value if isinstance(self.kind, MetricKind) else str(self.kind),
            "n_samples": int(self.n_samples),
            "coverage": float(self.coverage) if math.isfinite(self.coverage) else None,
            "confidence": float(self.confidence),
            "validity": (
                self.validity.value
                if isinstance(self.validity, Validity)
                else str(self.validity)
            ),
            "window_lo": _finite_or_none(self.window_lo),
            "window_hi": _finite_or_none(self.window_hi),
            "mad_raw": _finite_or_none(self.mad_raw),
            "mad_floor": float(self.mad_floor),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MetricPrior:
        try:
            kind = MetricKind(str(d.get("kind", "derived")))
        except ValueError:
            kind = MetricKind.DERIVED
        try:
            validity = Validity(str(d.get("validity", "abstain")))
        except ValueError:
            validity = Validity.ABSTAIN
        return cls(
            name=str(d["name"]),
            center=float(d.get("center") if d.get("center") is not None else float("nan")),
            scale=float(d.get("scale") if d.get("scale") is not None else float("nan")),
            units=str(d.get("units", "")),
            kind=kind,
            n_samples=int(d.get("n_samples", 0)),
            coverage=float(d.get("coverage") if d.get("coverage") is not None else 0.0),
            confidence=float(d.get("confidence", 0.05)),
            validity=validity,
            window_lo=float(
                d.get("window_lo") if d.get("window_lo") is not None else float("nan")
            ),
            window_hi=float(
                d.get("window_hi") if d.get("window_hi") is not None else float("nan")
            ),
            mad_raw=float(d.get("mad_raw") if d.get("mad_raw") is not None else float("nan")),
            mad_floor=float(d.get("mad_floor", 0.0)),
            reasons=list(d.get("reasons") or []),
        )


@dataclass
class PersonalBiomechPrior:
    """Serializable personal biomechanics prior (personal-baseline-v1)."""

    version: str = PERSONAL_BASELINE_VERSION
    metrics: dict[str, MetricPrior] = field(default_factory=dict)
    n_swings: int = 0
    min_samples: int = _DEFAULT_MIN_SAMPLES
    min_coverage: float = _DEFAULT_MIN_COVERAGE
    window_z: float = _WINDOW_Z
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        # Deterministic key order for stable JSON.
        ordered = {k: self.metrics[k].as_dict() for k in sorted(self.metrics)}
        return {
            "version": self.version,
            "n_swings": int(self.n_swings),
            "min_samples": int(self.min_samples),
            "min_coverage": float(self.min_coverage),
            "window_z": float(self.window_z),
            "metrics": ordered,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PersonalBiomechPrior:
        metrics_raw = d.get("metrics") or {}
        metrics = {
            str(k): MetricPrior.from_dict(v)
            for k, v in metrics_raw.items()
            if isinstance(v, Mapping)
        }
        return cls(
            version=str(d.get("version", PERSONAL_BASELINE_VERSION)),
            metrics=metrics,
            n_swings=int(d.get("n_swings", 0)),
            min_samples=int(d.get("min_samples", _DEFAULT_MIN_SAMPLES)),
            min_coverage=float(d.get("min_coverage", _DEFAULT_MIN_COVERAGE)),
            window_z=float(d.get("window_z", _WINDOW_Z)),
            meta=dict(d.get("meta") or {}),
        )

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.as_dict(), allow_nan=False, sort_keys=True, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> PersonalBiomechPrior:
        return cls.from_dict(json.loads(text))

    def usable(self, name: str) -> bool:
        m = self.metrics.get(name)
        return bool(m and m.validity in (Validity.OK, Validity.DEGRADED))


@dataclass
class MetricScore:
    """Signed personal (or tour-fallback) score for one metric."""

    name: str
    value: float
    signed_error: float
    z_score: float
    in_window: bool | None
    confidence: float
    validity: Validity
    residual: float
    units: str
    kind: MetricKind
    baseline: str  # personal | tour | none
    reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def as_metric_estimate(self) -> MetricEstimate:
        """Export as MetricEstimate: value = signed_error (personal delta)."""
        return MetricEstimate(
            name=f"delta_{self.name}",
            value=self.signed_error if self.validity != Validity.ABSTAIN else float("nan"),
            units=self.units,
            kind=MetricKind.DERIVED,
            confidence=self.confidence,
            validity=self.validity,
            residual=self.residual if math.isfinite(self.residual) else float("nan"),
            reasons=list(self.reasons),
            extras={
                "metric": self.name,
                "observed": _finite_or_none(self.value),
                "z_score": _finite_or_none(self.z_score),
                "in_window": self.in_window,
                "baseline": self.baseline,
                **dict(self.extras),
            },
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": _finite_or_none(self.value),
            "signed_error": _finite_or_none(self.signed_error),
            "z_score": _finite_or_none(self.z_score),
            "in_window": self.in_window,
            "confidence": float(self.confidence),
            "validity": (
                self.validity.value
                if isinstance(self.validity, Validity)
                else str(self.validity)
            ),
            "residual": _finite_or_none(self.residual),
            "units": self.units,
            "kind": self.kind.value if isinstance(self.kind, MetricKind) else str(self.kind),
            "baseline": self.baseline,
            "reasons": list(self.reasons),
            "extras": dict(self.extras),
        }


@dataclass
class PersonalScore:
    """Full personal scoring result for one swing."""

    version: str = PERSONAL_BASELINE_VERSION
    scores: dict[str, MetricScore] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        ordered = {k: self.scores[k].as_dict() for k in sorted(self.scores)}
        return {
            "version": self.version,
            "scores": ordered,
            "meta": dict(self.meta),
        }

    def deltas(self) -> list[MetricEstimate]:
        return [self.scores[k].as_metric_estimate() for k in sorted(self.scores)]


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    pairs = sorted(
        ((float(v), float(w)) for v, w in zip(values, weights) if math.isfinite(v) and w > 0),
        key=lambda p: p[0],
    )
    if not pairs:
        return float("nan")
    total = sum(w for _, w in pairs)
    if total <= 0:
        return float(pairs[len(pairs) // 2][0])
    acc = 0.0
    half = 0.5 * total
    for v, w in pairs:
        acc += w
        if acc >= half:
            return float(v)
    return float(pairs[-1][0])


def _weighted_mad(values: Sequence[float], weights: Sequence[float], center: float) -> float:
    deviations = [abs(float(v) - center) for v in values]
    return _weighted_median(deviations, weights)


def _is_usable_validity(v: Validity | str) -> bool:
    if isinstance(v, Validity):
        return v in (Validity.OK, Validity.DEGRADED)
    return str(v) in ("ok", "degraded")


def _face_calibrated_usable(metric: MetricEstimate) -> bool:
    """Face metrics require separate calibration flag — never infer by default."""
    extras = metric.extras or {}
    if extras.get("face_calibrated") is True:
        return True
    if extras.get("calibrated") is True and extras.get("head") == "club":
        return True
    reasons = set(metric.reasons or [])
    return "face_calibrated" in reasons or "calib_mae_within_ok_budget" in reasons


def extract_core_metrics(
    report: Any,
    *,
    include_face_if_calibrated: bool = True,
) -> dict[str, MetricEstimate]:
    """Extract core prior metrics from SwingReport or CommercialSwingReport."""
    # CommercialSwingReport path
    if hasattr(report, "truth") and isinstance(getattr(report, "truth", None), list):
        out: dict[str, MetricEstimate] = {}
        for m in report.truth:
            if isinstance(m, MetricEstimate) and m.name in CORE_PRIOR_METRICS:
                out[m.name] = m
        if include_face_if_calibrated and hasattr(report, "inference"):
            for m in report.inference or []:
                if (
                    isinstance(m, MetricEstimate)
                    and m.name in OPTIONAL_FACE_METRICS
                    and _is_usable_validity(m.validity)
                    and _face_calibrated_usable(m)
                ):
                    out[m.name] = m
        return out

    if isinstance(report, SwingReport) or (
        hasattr(report, "features") and hasattr(report, "meta")
    ):
        return _extract_from_swing_report(report, include_face_if_calibrated)

    if isinstance(report, Mapping):
        # Serialized commercial report or metric map
        if "truth" in report:
            out = {}
            for raw in report.get("truth") or []:
                if not isinstance(raw, Mapping):
                    continue
                name = str(raw.get("name", ""))
                if name not in CORE_PRIOR_METRICS:
                    continue
                out[name] = _metric_from_mapping(raw)
            return out
        # Flat metric dict
        out = {}
        for name in CORE_PRIOR_METRICS:
            if name in report and isinstance(report[name], (int, float)):
                out[name] = MetricEstimate(
                    name=name,
                    value=float(report[name]),
                    units=_METRIC_UNITS.get(name, "1"),
                    kind=MetricKind.DERIVED,
                    confidence=0.7,
                    validity=Validity.OK,
                )
        return out

    raise TypeError(f"unsupported report type for personal prior: {type(report)!r}")


def _metric_from_mapping(raw: Mapping[str, Any]) -> MetricEstimate:
    try:
        kind = MetricKind(str(raw.get("kind", "derived")))
    except ValueError:
        kind = MetricKind.DERIVED
    try:
        validity = Validity(str(raw.get("validity", "ok")))
    except ValueError:
        validity = Validity.ABSTAIN
    value = raw.get("value")
    residual = raw.get("residual")
    return MetricEstimate(
        name=str(raw["name"]),
        value=float(value) if value is not None else float("nan"),
        units=str(raw.get("units", "")),
        kind=kind,
        confidence=float(raw.get("confidence", 0.5)),
        validity=validity,
        residual=float(residual) if residual is not None else float("nan"),
        reasons=list(raw.get("reasons") or []),
        extras=dict(raw.get("extras") or {}),
    )


def _extract_from_swing_report(
    report: Any,
    include_face_if_calibrated: bool,
) -> dict[str, MetricEstimate]:
    f = report.features
    meta = report.meta if isinstance(report.meta, dict) else {}
    feat_q = meta.get("feature_quality") if isinstance(meta.get("feature_quality"), dict) else {}

    def _layer(name: str) -> dict[str, Any]:
        layer = feat_q.get(name) if isinstance(feat_q, dict) else None
        return layer if isinstance(layer, dict) else {}

    def _vq(layer: dict[str, Any], default_v: Validity, default_c: float) -> tuple[Validity, float, list[str]]:
        if not layer:
            return default_v, default_c, []
        try:
            v = Validity(str(layer.get("validity", default_v.value)))
        except ValueError:
            v = default_v
        c = clip_confidence(float(layer.get("confidence", default_c)))
        return v, c, list(layer.get("reasons") or [])

    radius = float("nan")
    if "radius_m" in meta:
        try:
            radius = float(meta["radius_m"])
        except (TypeError, ValueError):
            radius = float("nan")

    timing_v, timing_c, timing_r = _vq(_layer("tempo"), Validity.OK, 0.8)
    peak_v, peak_c, peak_r = _vq(_layer("peak_omega"), Validity.OK, 0.85)
    plane_v, plane_c, plane_r = _vq(_layer("plane"), Validity.DEGRADED, 0.55)
    path_v, path_c, path_r = _vq(_layer("path"), Validity.DEGRADED, 0.55)

    specs: list[tuple[str, float, str, Validity, float, list[str], MetricKind]] = [
        ("tempo_s", float(f.tempo_s), "s", timing_v, timing_c, timing_r, MetricKind.DERIVED),
        ("rhythm", float(f.rhythm), "1", timing_v, timing_c, timing_r, MetricKind.DERIVED),
        (
            "peak_omega_to_impact_s",
            float(f.peak_omega_to_impact_s),
            "s",
            timing_v,
            timing_c,
            timing_r,
            MetricKind.DERIVED,
        ),
        (
            "peak_omega_rad_s",
            float(f.peak_omega_rad_s),
            "rad/s",
            peak_v,
            peak_c,
            peak_r,
            MetricKind.MEASURED,
        ),
        (
            "plane_angle_deg",
            float(f.plane_angle_deg),
            "deg",
            plane_v,
            plane_c,
            plane_r,
            MetricKind.DERIVED,
        ),
        (
            "hand_speed_peak_m_s",
            float(f.hand_speed_peak_m_s),
            "m/s",
            path_v,
            path_c,
            path_r,
            MetricKind.DERIVED,
        ),
        (
            "trajectory_radius_m",
            float(radius),
            "m",
            path_v,
            path_c,
            path_r,
            MetricKind.DERIVED,
        ),
    ]
    out: dict[str, MetricEstimate] = {}
    for name, value, units, validity, conf, reasons, kind in specs:
        if not math.isfinite(value):
            validity = Validity.ABSTAIN
            conf = min(conf, 0.1)
            reasons = list(reasons) + ["value_unavailable"]
        out[name] = MetricEstimate(
            name=name,
            value=value,
            units=units,
            kind=kind,
            confidence=clip_confidence(conf),
            validity=validity,
            reasons=list(reasons),
        )

    if include_face_if_calibrated:
        high = meta.get("high_order") if isinstance(meta.get("high_order"), dict) else None
        if high:
            club = high.get("club") if isinstance(high.get("club"), dict) else {}
            metrics = club.get("metrics") if isinstance(club.get("metrics"), dict) else {}
            face_entry = metrics.get("face_impact") if isinstance(metrics, dict) else None
            face_val = club.get("face_impact_deg", float("nan"))
            try:
                face_v = Validity(str(
                    (face_entry or {}).get("validity", club.get("validity", "abstain"))
                ))
            except ValueError:
                face_v = Validity.ABSTAIN
            face_c = float(
                (face_entry or {}).get("confidence", club.get("confidence", 0.1))
            )
            face_reasons = list(
                (face_entry or {}).get("reasons") or club.get("reasons") or []
            )
            candidate = MetricEstimate(
                name="clubface_impact_deg",
                value=float(face_val) if face_val is not None else float("nan"),
                units="deg",
                kind=MetricKind.INFERRED,
                confidence=clip_confidence(face_c),
                validity=face_v,
                reasons=face_reasons,
                extras={
                    "head": "club",
                    "calibrated": "calib_mae_within_ok_budget" in set(face_reasons),
                    "face_calibrated": "calib_mae_within_ok_budget" in set(face_reasons),
                },
            )
            if (
                _is_usable_validity(candidate.validity)
                and _face_calibrated_usable(candidate)
                and math.isfinite(candidate.value)
            ):
                out["clubface_impact_deg"] = candidate
    return out


def fit_personal_prior(
    reports: Sequence[Any],
    *,
    min_samples: int = _DEFAULT_MIN_SAMPLES,
    min_coverage: float = _DEFAULT_MIN_COVERAGE,
    window_z: float = _WINDOW_Z,
    outlier_z: float = _OUTLIER_Z,
    include_face_if_calibrated: bool = True,
    metric_names: Sequence[str] | None = None,
) -> PersonalBiomechPrior:
    """Fit a robust PersonalBiomechPrior from a sequence of reports.

    Outliers and abstained metrics are excluded so they cannot contaminate
    center/scale. Confidence weights soft-emphasize higher-quality samples.
    """
    names = list(metric_names) if metric_names is not None else list(CORE_PRIOR_METRICS)
    # Collect per-metric observations
    buckets: dict[str, list[tuple[float, float, MetricKind, str]]] = {n: [] for n in names}
    n_swings = 0
    for report in reports:
        metrics = extract_core_metrics(
            report, include_face_if_calibrated=include_face_if_calibrated
        )
        n_swings += 1
        for name in names:
            m = metrics.get(name)
            if m is None:
                continue
            if name in OPTIONAL_FACE_METRICS and not _face_calibrated_usable(m):
                continue
            if not _is_usable_validity(m.validity):
                continue
            if not math.isfinite(m.value):
                continue
            # Soft weight: degraded samples contribute less.
            w = float(m.confidence)
            if m.validity == Validity.DEGRADED:
                w *= 0.65
            if w <= 0:
                continue
            buckets.setdefault(name, []).append(
                (float(m.value), w, m.kind, m.units or _METRIC_UNITS.get(name, "1"))
            )
        # Allow calibrated face to appear even if not in names list default.
        if include_face_if_calibrated:
            for face_name in OPTIONAL_FACE_METRICS:
                if face_name in names:
                    continue
                m = metrics.get(face_name)
                if m is None or not _face_calibrated_usable(m):
                    continue
                if not _is_usable_validity(m.validity) or not math.isfinite(m.value):
                    continue
                w = float(m.confidence) * (0.65 if m.validity == Validity.DEGRADED else 1.0)
                buckets.setdefault(face_name, []).append(
                    (float(m.value), w, m.kind, m.units or "deg")
                )

    fitted: dict[str, MetricPrior] = {}
    all_names = sorted(set(names) | set(buckets.keys()))
    for name in all_names:
        samples = buckets.get(name) or []
        fitted[name] = _fit_one_metric(
            name,
            samples,
            n_swings=n_swings,
            min_samples=min_samples,
            min_coverage=min_coverage,
            window_z=window_z,
            outlier_z=outlier_z,
        )

    return PersonalBiomechPrior(
        version=PERSONAL_BASELINE_VERSION,
        metrics=fitted,
        n_swings=n_swings,
        min_samples=min_samples,
        min_coverage=min_coverage,
        window_z=window_z,
        meta={
            "core_metrics": list(CORE_PRIOR_METRICS),
            "outlier_z": float(outlier_z),
            "include_face_if_calibrated": bool(include_face_if_calibrated),
            "fit": "weighted_median_mad",
        },
    )


def _fit_one_metric(
    name: str,
    samples: Sequence[tuple[float, float, MetricKind, str]],
    *,
    n_swings: int,
    min_samples: int,
    min_coverage: float,
    window_z: float,
    outlier_z: float,
) -> MetricPrior:
    units = _METRIC_UNITS.get(name, samples[0][3] if samples else "1")
    kind = samples[0][2] if samples else MetricKind.DERIVED
    floor = float(_MAD_FLOORS.get(name, 1e-3))
    coverage = (len(samples) / n_swings) if n_swings > 0 else 0.0
    reasons: list[str] = []

    if len(samples) < min_samples:
        reasons.append("min_samples_not_met")
        return MetricPrior(
            name=name,
            center=float("nan"),
            scale=float("nan"),
            units=units,
            kind=kind,
            n_samples=len(samples),
            coverage=coverage,
            confidence=0.05,
            validity=Validity.ABSTAIN,
            window_lo=float("nan"),
            window_hi=float("nan"),
            mad_raw=float("nan"),
            mad_floor=floor,
            reasons=reasons,
        )
    if coverage < min_coverage:
        reasons.append("min_coverage_not_met")
        return MetricPrior(
            name=name,
            center=float("nan"),
            scale=float("nan"),
            units=units,
            kind=kind,
            n_samples=len(samples),
            coverage=coverage,
            confidence=0.05,
            validity=Validity.ABSTAIN,
            window_lo=float("nan"),
            window_hi=float("nan"),
            mad_raw=float("nan"),
            mad_floor=floor,
            reasons=reasons,
        )

    values = [v for v, _, _, _ in samples]
    weights = [w for _, w, _, _ in samples]
    center = _weighted_median(values, weights)
    mad_raw = _weighted_mad(values, weights, center)
    scale0 = max(1.4826 * mad_raw, floor)

    # Robust outlier rejection — exclude extreme samples then re-estimate.
    kept_v: list[float] = []
    kept_w: list[float] = []
    n_outliers = 0
    for v, w in zip(values, weights):
        z = abs(v - center) / scale0
        if z > outlier_z:
            n_outliers += 1
            continue
        kept_v.append(v)
        kept_w.append(w)

    if len(kept_v) < min_samples:
        reasons.append("min_samples_after_outlier_reject")
        return MetricPrior(
            name=name,
            center=float("nan"),
            scale=float("nan"),
            units=units,
            kind=kind,
            n_samples=len(kept_v),
            coverage=coverage,
            confidence=0.05,
            validity=Validity.ABSTAIN,
            window_lo=float("nan"),
            window_hi=float("nan"),
            mad_raw=mad_raw,
            mad_floor=floor,
            reasons=reasons + ["outliers_rejected"],
        )

    center = _weighted_median(kept_v, kept_w)
    mad_raw = _weighted_mad(kept_v, kept_w, center)
    scale = max(1.4826 * mad_raw, floor)
    if n_outliers:
        reasons.append("outliers_rejected")

    mean_w = sum(kept_w) / max(len(kept_w), 1)
    conf = clip_confidence(0.35 + 0.5 * mean_w + 0.1 * min(1.0, len(kept_v) / 12.0))
    validity = Validity.OK
    if coverage < 0.7 or mean_w < 0.55 or n_outliers > 0:
        validity = Validity.DEGRADED
        if coverage < 0.7:
            reasons.append("partial_coverage")
        if mean_w < 0.55:
            reasons.append("low_mean_confidence")

    half = window_z * scale
    return MetricPrior(
        name=name,
        center=float(center),
        scale=float(scale),
        units=units,
        kind=kind,
        n_samples=len(kept_v),
        coverage=float(coverage),
        confidence=conf,
        validity=validity,
        window_lo=float(center - half),
        window_hi=float(center + half),
        mad_raw=float(mad_raw),
        mad_floor=floor,
        reasons=reasons,
    )


def _tour_fallback(name: str) -> MetricPrior | None:
    """Tour/ideal band fallback when personal prior abstains for a metric."""
    tmpl = load_ideal_template()
    band = tmpl.bands.get(name)
    if band is None:
        return None
    center = float(band.p50)
    iqr = max(float(band.p75) - float(band.p25), 1e-9)
    # IQR ≈ 1.349 σ for normal; convert to robust scale.
    scale = max(iqr / 1.349, float(_MAD_FLOORS.get(name, 1e-3)))
    half = _WINDOW_Z * scale
    return MetricPrior(
        name=name,
        center=center,
        scale=scale,
        units=_METRIC_UNITS.get(name, "1"),
        kind=MetricKind.DERIVED,
        n_samples=int(tmpl.n_train),
        coverage=1.0,
        confidence=0.45,
        validity=Validity.DEGRADED,
        window_lo=center - half,
        window_hi=center + half,
        mad_raw=scale / 1.4826,
        mad_floor=float(_MAD_FLOORS.get(name, 1e-3)),
        reasons=["tour_ideal_fallback"],
    )


def score_against_prior(
    report: Any,
    prior: PersonalBiomechPrior | None,
    *,
    prefer_personal: bool = True,
    allow_tour_fallback: bool = True,
    include_face_if_calibrated: bool = True,
) -> PersonalScore:
    """Score a swing with signed errors vs personal baseline (tour fallback)."""
    observed = extract_core_metrics(
        report, include_face_if_calibrated=include_face_if_calibrated
    )
    names = set(CORE_PRIOR_METRICS)
    if prior is not None:
        names |= set(prior.metrics.keys())
    names |= set(observed.keys())

    scores: dict[str, MetricScore] = {}
    for name in sorted(names):
        m = observed.get(name)
        personal = prior.metrics.get(name) if prior is not None else None
        baseline_prior: MetricPrior | None = None
        baseline = "none"
        reasons: list[str] = []

        if prefer_personal and personal is not None and personal.validity in (
            Validity.OK,
            Validity.DEGRADED,
        ):
            baseline_prior = personal
            baseline = "personal"
        elif allow_tour_fallback:
            tour = _tour_fallback(name)
            if tour is not None:
                baseline_prior = tour
                baseline = "tour"
                reasons.append("personal_unavailable_tour_fallback")
            elif personal is not None:
                baseline_prior = personal
                baseline = "personal"
                reasons.append("personal_abstained")
        elif personal is not None:
            baseline_prior = personal
            baseline = "personal"

        if m is None or not math.isfinite(m.value):
            scores[name] = MetricScore(
                name=name,
                value=float("nan"),
                signed_error=float("nan"),
                z_score=float("nan"),
                in_window=None,
                confidence=0.05,
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                units=_METRIC_UNITS.get(name, "1"),
                kind=MetricKind.DERIVED,
                baseline=baseline,
                reasons=reasons + ["observation_unavailable"],
            )
            continue

        if not _is_usable_validity(m.validity):
            scores[name] = MetricScore(
                name=name,
                value=float(m.value),
                signed_error=float("nan"),
                z_score=float("nan"),
                in_window=None,
                confidence=min(float(m.confidence), 0.15),
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                units=m.units or _METRIC_UNITS.get(name, "1"),
                kind=m.kind,
                baseline=baseline,
                reasons=reasons + ["observation_abstained"] + list(m.reasons or []),
            )
            continue

        if baseline_prior is None or baseline_prior.validity == Validity.ABSTAIN:
            scores[name] = MetricScore(
                name=name,
                value=float(m.value),
                signed_error=float("nan"),
                z_score=float("nan"),
                in_window=None,
                confidence=min(float(m.confidence), 0.2),
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                units=m.units or _METRIC_UNITS.get(name, "1"),
                kind=m.kind,
                baseline=baseline,
                reasons=reasons + ["baseline_unavailable"],
            )
            continue

        if not math.isfinite(baseline_prior.center) or not math.isfinite(baseline_prior.scale):
            scores[name] = MetricScore(
                name=name,
                value=float(m.value),
                signed_error=float("nan"),
                z_score=float("nan"),
                in_window=None,
                confidence=0.1,
                validity=Validity.ABSTAIN,
                residual=float("nan"),
                units=m.units or _METRIC_UNITS.get(name, "1"),
                kind=m.kind,
                baseline=baseline,
                reasons=reasons + ["baseline_nonfinite"],
            )
            continue

        signed = float(m.value) - float(baseline_prior.center)
        z = signed / float(baseline_prior.scale)
        in_window = abs(z) <= float(
            prior.window_z if prior is not None else _WINDOW_Z
        )
        conf = clip_confidence(
            0.5 * float(m.confidence) + 0.5 * float(baseline_prior.confidence)
        )
        validity = Validity.OK
        if m.validity == Validity.DEGRADED or baseline_prior.validity == Validity.DEGRADED:
            validity = Validity.DEGRADED
            reasons.append("degraded_observation_or_baseline")
        scores[name] = MetricScore(
            name=name,
            value=float(m.value),
            signed_error=float(signed),
            z_score=float(z),
            in_window=bool(in_window),
            confidence=conf,
            validity=validity,
            residual=abs(float(z)),
            units=m.units or _METRIC_UNITS.get(name, "1"),
            kind=m.kind,
            baseline=baseline,
            reasons=reasons + list(baseline_prior.reasons or []),
            extras={
                "center": baseline_prior.center,
                "scale": baseline_prior.scale,
                "window_lo": baseline_prior.window_lo,
                "window_hi": baseline_prior.window_hi,
            },
        )

    return PersonalScore(
        version=PERSONAL_BASELINE_VERSION,
        scores=scores,
        meta={
            "prefer_personal": bool(prefer_personal),
            "allow_tour_fallback": bool(allow_tour_fallback),
            "prior_n_swings": int(prior.n_swings) if prior is not None else 0,
        },
    )


def load_personal_baseline_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


__all__ = [
    "CORE_PRIOR_METRICS",
    "OPTIONAL_FACE_METRICS",
    "PERSONAL_BASELINE_VERSION",
    "MetricPrior",
    "MetricScore",
    "PersonalBiomechPrior",
    "PersonalScore",
    "extract_core_metrics",
    "fit_personal_prior",
    "load_personal_baseline_schema",
    "score_against_prior",
]
