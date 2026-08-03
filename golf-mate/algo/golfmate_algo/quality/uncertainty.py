"""Observability-aware validity / uncertainty for coaching outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricKind(str, Enum):
    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"
    PROXY = "proxy"


class Validity(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    ABSTAIN = "abstain"


@dataclass
class MetricEstimate:
    name: str
    value: float
    units: str
    kind: MetricKind
    confidence: float
    validity: Validity
    reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


def clip_confidence(x: float) -> float:
    return float(max(0.05, min(0.95, x)))


def fuse_confidence(*parts: float, weights: list[float] | None = None) -> float:
    vals = [float(p) for p in parts if p is not None]
    if not vals:
        return 0.2
    if weights is None:
        return clip_confidence(float(sum(vals) / len(vals)))
    w = list(weights)[: len(vals)]
    s = sum(w) + 1e-9
    return clip_confidence(float(sum(v * wi for v, wi in zip(vals, w)) / s))


def trajectory_validity(
    *,
    radius_m: float,
    residual_rms: float,
    rank: float,
    fallback: float,
) -> tuple[Validity, list[str], float]:
    reasons: list[str] = []
    conf = 0.7
    if rank < 2:
        reasons.append("lever_rank_low")
        conf *= 0.4
    if radius_m < 0.15 or radius_m > 1.5:
        reasons.append("radius_implausible")
        conf *= 0.5
    if residual_rms > 15.0:
        reasons.append("rigid_residual_high")
        conf *= 0.6
    if fallback > 0.5:
        reasons.append("trajectory_fallback")
        conf *= 0.5
    conf = clip_confidence(conf)
    if conf < 0.25 or "lever_rank_low" in reasons:
        return Validity.ABSTAIN, reasons, conf
    if reasons:
        return Validity.DEGRADED, reasons, conf
    return Validity.OK, reasons, conf


def release_validity(
    *,
    impact_mode: str,
    release_confidence: float,
    peak_omega: float,
) -> tuple[Validity, list[str], float]:
    reasons: list[str] = []
    conf = float(release_confidence)
    if impact_mode == "unavailable":
        reasons.append("impact_unavailable")
        conf *= 0.4
    elif impact_mode == "kinematic_proxy":
        reasons.append("impact_kinematic_proxy")
        conf *= 0.75
    if peak_omega < 2.0:
        reasons.append("low_peak_omega")
        conf *= 0.5
    conf = clip_confidence(conf)
    if conf < 0.2:
        return Validity.ABSTAIN, reasons, conf
    if reasons:
        return Validity.DEGRADED, reasons, conf
    return Validity.OK, reasons, conf
