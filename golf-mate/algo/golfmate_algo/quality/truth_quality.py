"""Commercial truth-layer quality evaluation.

Per-layer validity / confidence / reasons for impact, AHRS, trajectory,
strap-slip, and sensor saturation/drop. Never silently claims collision or
trajectory when the underlying evidence does not support it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.quality.uncertainty import (
    Validity,
    clip_confidence,
    fuse_confidence,
    trajectory_validity,
)

ArrayF = NDArray[np.float64]

# Commercial impact provenance (export contract). Internal segmental may still
# use ``kinematic_proxy`` / ``unavailable``; this maps them explicitly.
IMPACT_PROVENANCE_COLLISION = "collision"
IMPACT_PROVENANCE_KINEMATIC = "kinematic"
IMPACT_PROVENANCE_ABSTAIN = "abstain"


def commercial_impact_provenance(impact_mode: str | None) -> str:
    """Map internal impact_mode → commercial provenance collision|kinematic|abstain."""
    mode = str(impact_mode or "unknown").lower().strip()
    if mode in {"collision", "high_rate_impact_hint"}:
        return IMPACT_PROVENANCE_COLLISION
    if mode in {"kinematic_proxy", "kinematic"}:
        return IMPACT_PROVENANCE_KINEMATIC
    # unavailable / abstain / unknown / anything else
    return IMPACT_PROVENANCE_ABSTAIN


@dataclass
class LayerQuality:
    """Single observability layer with explicit validity semantics."""

    name: str
    validity: Validity
    confidence: float
    reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "validity": self.validity.value
            if isinstance(self.validity, Validity)
            else str(self.validity),
            "confidence": float(self.confidence),
            "reasons": list(self.reasons),
            "extras": dict(self.extras),
        }


@dataclass
class TruthQualityReport:
    """Aggregated commercial truth-layer evaluation."""

    layers: dict[str, LayerQuality]
    overall_validity: Validity
    overall_confidence: float
    impact_provenance: str
    reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "layers": {k: v.as_dict() for k, v in self.layers.items()},
            "overall_validity": self.overall_validity.value
            if isinstance(self.overall_validity, Validity)
            else str(self.overall_validity),
            "overall_confidence": float(self.overall_confidence),
            "impact_provenance": self.impact_provenance,
            "reasons": list(self.reasons),
            "extras": dict(self.extras),
        }

    def layer(self, name: str) -> LayerQuality | None:
        return self.layers.get(name)


def evaluate_impact_layer(
    *,
    impact_mode: str,
    impact_confidence: float = 0.5,
    impact_method: str | None = None,
) -> LayerQuality:
    provenance = commercial_impact_provenance(impact_mode)
    reasons: list[str] = []
    conf = float(impact_confidence) if math.isfinite(float(impact_confidence)) else 0.3
    extras: dict[str, Any] = {
        "impact_mode_internal": str(impact_mode),
        "impact_provenance": provenance,
        "impact_method": impact_method,
    }

    if provenance == IMPACT_PROVENANCE_COLLISION:
        validity = Validity.OK if conf >= 0.35 else Validity.DEGRADED
        if conf < 0.35:
            reasons.append("collision_low_confidence")
        return LayerQuality("impact", validity, clip_confidence(conf), reasons, extras)

    if provenance == IMPACT_PROVENANCE_KINEMATIC:
        reasons.append("impact_kinematic_not_collision")
        # Never claim collision when only kinematic evidence exists.
        conf = clip_confidence(min(conf, 0.55) * 0.85)
        return LayerQuality("impact", Validity.DEGRADED, conf, reasons, extras)

    reasons.append("impact_unavailable")
    conf = clip_confidence(min(conf, 0.2) * 0.5)
    return LayerQuality("impact", Validity.ABSTAIN, conf, reasons, extras)


def evaluate_ahrs_layer(
    *,
    gate: ArrayLike | None = None,
    bias: ArrayLike | None = None,
    innovation_deg: ArrayLike | None = None,
    rest_mask: ArrayLike | None = None,
) -> LayerQuality:
    reasons: list[str] = []
    conf = 0.75
    extras: dict[str, Any] = {}

    gate_arr = None if gate is None else np.asarray(gate, dtype=np.float64).reshape(-1)
    bias_arr = None if bias is None else np.asarray(bias, dtype=np.float64)
    innov = (
        None
        if innovation_deg is None
        else np.asarray(innovation_deg, dtype=np.float64).reshape(-1)
    )
    rest = None if rest_mask is None else np.asarray(rest_mask, dtype=bool).reshape(-1)

    if gate_arr is not None and gate_arr.size:
        mean_gate = float(np.nanmean(gate_arr))
        extras["mean_gate"] = mean_gate
        # Low mean gate during a full swing is expected (dynamics close tilt);
        # flag only pathological always-open or NaN gates.
        if not math.isfinite(mean_gate):
            reasons.append("ahrs_gate_nonfinite")
            conf *= 0.4
        elif mean_gate > 0.95:
            reasons.append("ahrs_gate_always_open")
            conf *= 0.7

    if bias_arr is not None and bias_arr.size:
        b = bias_arr.reshape(-1, 3) if bias_arr.ndim == 2 else bias_arr.reshape(1, 3)
        bias_norm = float(np.linalg.norm(b[-1]))
        extras["bias_norm_rad_s"] = bias_norm
        if bias_norm > 0.35:  # ~20 deg/s — large residual bias
            reasons.append("ahrs_bias_high")
            conf *= 0.6
        if b.shape[0] >= 8:
            drift = float(np.linalg.norm(b[-1] - b[b.shape[0] // 2]))
            extras["bias_drift_rad_s"] = drift
            if drift > 0.15:
                reasons.append("ahrs_bias_drift")
                conf *= 0.75

    if innov is not None and innov.size:
        finite = innov[np.isfinite(innov)]
        if finite.size:
            if rest is not None and rest.shape[0] == innov.shape[0] and rest.any():
                rest_innov = innov[rest]
                rest_innov = rest_innov[np.isfinite(rest_innov)]
                mean_rest = float(np.mean(rest_innov)) if rest_innov.size else float("nan")
            else:
                mean_rest = float(np.nanmean(finite[: max(1, finite.size // 10)]))
            extras["rest_innovation_deg"] = mean_rest
            if math.isfinite(mean_rest) and mean_rest > 12.0:
                reasons.append("ahrs_innovation_high")
                conf *= 0.55
            p95 = float(np.nanpercentile(finite, 95))
            extras["innovation_p95_deg"] = p95
            if p95 > 45.0:
                reasons.append("ahrs_innovation_p95_high")
                conf *= 0.7

    conf = clip_confidence(conf)
    if conf < 0.25 or "ahrs_gate_nonfinite" in reasons:
        validity = Validity.ABSTAIN
    elif reasons:
        validity = Validity.DEGRADED
    else:
        validity = Validity.OK
    return LayerQuality("ahrs", validity, conf, reasons, extras)


def evaluate_trajectory_layer(
    *,
    radius_m: float,
    residual_rms: float,
    rank: float,
    fallback: float,
    valid_flag: float | bool | None = None,
) -> LayerQuality:
    validity, reasons, conf = trajectory_validity(
        radius_m=float(radius_m) if math.isfinite(float(radius_m)) else 0.0,
        residual_rms=float(residual_rms) if math.isfinite(float(residual_rms)) else 99.0,
        rank=float(rank) if math.isfinite(float(rank)) else 0.0,
        fallback=float(fallback) if math.isfinite(float(fallback)) else 1.0,
    )
    extras: dict[str, Any] = {
        "radius_m": float(radius_m) if math.isfinite(float(radius_m)) else None,
        "residual_rms_m_s2": float(residual_rms)
        if math.isfinite(float(residual_rms))
        else None,
        "rank": float(rank) if math.isfinite(float(rank)) else None,
        "fallback": float(fallback) if math.isfinite(float(fallback)) else None,
    }
    if valid_flag is not None and not bool(valid_flag) and validity == Validity.OK:
        reasons = list(reasons) + ["trajectory_flagged_invalid"]
        conf = clip_confidence(conf * 0.6)
        validity = Validity.DEGRADED
    # Explicit: never claim a usable trajectory when abstained.
    if validity == Validity.ABSTAIN and "trajectory_unavailable" not in reasons:
        reasons = list(reasons) + ["trajectory_unavailable"]
    return LayerQuality("trajectory", validity, conf, reasons, extras)


def evaluate_strap_slip_layer(
    *,
    strap_slip_score: float = 0.0,
    strap_slip_detected: bool | float = False,
    lever_angle_delta_deg: float = 0.0,
    radius_ratio: float = 1.0,
) -> LayerQuality:
    reasons: list[str] = []
    detected = bool(strap_slip_detected) or float(strap_slip_score) >= 0.55
    score = float(strap_slip_score) if math.isfinite(float(strap_slip_score)) else 0.0
    extras = {
        "strap_slip_score": score,
        "strap_slip_detected": float(1.0 if detected else 0.0),
        "lever_angle_delta_deg": float(lever_angle_delta_deg)
        if math.isfinite(float(lever_angle_delta_deg))
        else None,
        "radius_ratio": float(radius_ratio) if math.isfinite(float(radius_ratio)) else None,
    }
    if detected:
        reasons.append("strap_slip_detected")
        conf = clip_confidence(0.25 + 0.2 * (1.0 - min(score, 1.0)))
        return LayerQuality("strap_slip", Validity.ABSTAIN, conf, reasons, extras)
    if score >= 0.30:
        reasons.append("strap_slip_elevated")
        conf = clip_confidence(0.55)
        return LayerQuality("strap_slip", Validity.DEGRADED, conf, reasons, extras)
    return LayerQuality("strap_slip", Validity.OK, clip_confidence(0.85), reasons, extras)


def evaluate_sensor_layer(
    *,
    gyro: ArrayLike | None = None,
    accel: ArrayLike | None = None,
    t: ArrayLike | None = None,
    gyro_range_rad_s: float = np.radians(2000.0),
    accel_range_m_s2: float = 16.0 * 9.80665,
    saturation_frac_thresh: float = 0.002,
    drop_irregularity_thresh: float = 0.05,
) -> LayerQuality:
    reasons: list[str] = []
    conf = 0.85
    extras: dict[str, Any] = {}

    sat_frac = 0.0
    if gyro is not None:
        g = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
        g_lim = 0.98 * float(gyro_range_rad_s)
        g_sat = np.any(np.abs(g) >= g_lim, axis=1)
        sat_frac = max(sat_frac, float(np.mean(g_sat))) if g.shape[0] else 0.0
        extras["gyro_sat_frac"] = float(np.mean(g_sat)) if g.shape[0] else 0.0
        if not np.all(np.isfinite(g)):
            reasons.append("gyro_nonfinite")
            conf *= 0.4
    if accel is not None:
        a = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
        a_lim = 0.98 * float(accel_range_m_s2)
        a_sat = np.any(np.abs(a) >= a_lim, axis=1)
        sat_frac = max(sat_frac, float(np.mean(a_sat))) if a.shape[0] else sat_frac
        extras["accel_sat_frac"] = float(np.mean(a_sat)) if a.shape[0] else 0.0
        if not np.all(np.isfinite(a)):
            reasons.append("accel_nonfinite")
            conf *= 0.4
    extras["saturation_frac"] = sat_frac
    if sat_frac >= saturation_frac_thresh:
        reasons.append("sensor_saturation")
        conf *= max(0.35, 1.0 - 8.0 * sat_frac)

    drop_irreg = 0.0
    if t is not None:
        tt = np.asarray(t, dtype=np.float64).reshape(-1)
        if tt.size >= 3:
            dts = np.diff(tt)
            med = float(np.median(dts))
            if med > 1e-9:
                drop_irreg = float(np.std(dts) / med)
                # Large positive gaps relative to median ⇒ dropouts / jitter.
                gap_frac = float(np.mean(dts > 2.5 * med))
                extras["dt_cv"] = drop_irreg
                extras["gap_frac"] = gap_frac
                if drop_irreg >= drop_irregularity_thresh or gap_frac >= 0.02:
                    reasons.append("timestamp_drop_irregularity")
                    conf *= 0.55
    extras["drop_irregularity"] = drop_irreg

    conf = clip_confidence(conf)
    if "gyro_nonfinite" in reasons or "accel_nonfinite" in reasons or sat_frac >= 0.05:
        validity = Validity.ABSTAIN
    elif reasons:
        validity = Validity.DEGRADED
    else:
        validity = Validity.OK
    return LayerQuality("sensor", validity, conf, reasons, extras)


def _worst_validity(*vals: Validity) -> Validity:
    order = {Validity.OK: 0, Validity.DEGRADED: 1, Validity.ABSTAIN: 2}
    worst = Validity.OK
    for v in vals:
        if order[v] > order[worst]:
            worst = v
    return worst


def evaluate_truth_quality(
    *,
    impact_mode: str,
    impact_confidence: float = 0.5,
    impact_method: str | None = None,
    radius_m: float = float("nan"),
    residual_rms: float = float("nan"),
    rank: float = float("nan"),
    fallback: float = 0.0,
    traj_valid: float | bool | None = None,
    strap_slip_score: float = 0.0,
    strap_slip_detected: bool | float = False,
    lever_angle_delta_deg: float = 0.0,
    radius_ratio: float = 1.0,
    gate: ArrayLike | None = None,
    bias: ArrayLike | None = None,
    innovation_deg: ArrayLike | None = None,
    rest_mask: ArrayLike | None = None,
    gyro: ArrayLike | None = None,
    accel: ArrayLike | None = None,
    t: ArrayLike | None = None,
) -> TruthQualityReport:
    """Evaluate all commercial truth layers and aggregate."""
    impact = evaluate_impact_layer(
        impact_mode=impact_mode,
        impact_confidence=impact_confidence,
        impact_method=impact_method,
    )
    ahrs = evaluate_ahrs_layer(
        gate=gate, bias=bias, innovation_deg=innovation_deg, rest_mask=rest_mask
    )
    traj = evaluate_trajectory_layer(
        radius_m=radius_m,
        residual_rms=residual_rms,
        rank=rank,
        fallback=fallback,
        valid_flag=traj_valid,
    )
    strap = evaluate_strap_slip_layer(
        strap_slip_score=strap_slip_score,
        strap_slip_detected=strap_slip_detected,
        lever_angle_delta_deg=lever_angle_delta_deg,
        radius_ratio=radius_ratio,
    )
    sensor = evaluate_sensor_layer(gyro=gyro, accel=accel, t=t)

    layers = {
        "impact": impact,
        "ahrs": ahrs,
        "trajectory": traj,
        "strap_slip": strap,
        "sensor": sensor,
    }
    overall = _worst_validity(*(L.validity for L in layers.values()))
    overall_conf = fuse_confidence(*(L.confidence for L in layers.values()))
    reasons: list[str] = []
    for L in layers.values():
        reasons.extend(L.reasons)

    # Honesty: if impact abstains, do not allow overall to look cleaner than impact.
    provenance = commercial_impact_provenance(impact_mode)
    if provenance == IMPACT_PROVENANCE_ABSTAIN and overall == Validity.OK:
        overall = Validity.ABSTAIN
    if traj.validity == Validity.ABSTAIN and overall == Validity.OK:
        overall = Validity.ABSTAIN

    return TruthQualityReport(
        layers=layers,
        overall_validity=overall,
        overall_confidence=overall_conf,
        impact_provenance=provenance,
        reasons=sorted(set(reasons)),
        extras={},
    )


def feature_quality_from_truth(
    *,
    truth: TruthQualityReport,
    peak_omega_rad_s: float,
    plane_residual_rms: float,
    channel_kind: str = "unknown_segment",
    rigidity_fail: bool | float = False,
    casting_observability_ok: bool | None = None,
) -> dict[str, LayerQuality]:
    """P0 commercial feature quality: tempo/rhythm/transition/peak/path/plane/casting.

    Casting abstains when mount/observability does not support a wrist-release
    timing claim (club-mount rigidity failure, abstained trajectory/impact, or
    non-wrist channel without explicit observability).
    """
    impact = truth.layer("impact") or LayerQuality("impact", Validity.ABSTAIN, 0.1)
    traj = truth.layer("trajectory") or LayerQuality("trajectory", Validity.ABSTAIN, 0.1)
    ahrs = truth.layer("ahrs") or LayerQuality("ahrs", Validity.DEGRADED, 0.4)
    strap = truth.layer("strap_slip") or LayerQuality("strap_slip", Validity.OK, 0.7)
    sensor = truth.layer("sensor") or LayerQuality("sensor", Validity.OK, 0.7)

    timing_v = impact.validity
    timing_conf = fuse_confidence(impact.confidence, ahrs.confidence, sensor.confidence)
    timing_reasons = list(impact.reasons)
    if sensor.validity != Validity.OK:
        timing_reasons.extend(sensor.reasons)
    if strap.validity == Validity.ABSTAIN:
        timing_v = Validity.ABSTAIN
        timing_conf = clip_confidence(timing_conf * 0.4)
        timing_reasons.append("strap_slip_blocks_timing")

    peak_reasons: list[str] = []
    peak_conf = 0.9 if peak_omega_rad_s > 2.0 else 0.45
    peak_v = Validity.OK if peak_omega_rad_s > 2.0 else Validity.DEGRADED
    if peak_omega_rad_s <= 2.0:
        peak_reasons.append("low_peak_omega")
    if sensor.validity == Validity.ABSTAIN:
        peak_v = Validity.ABSTAIN
        peak_reasons.append("sensor_abstain")
        peak_conf *= 0.3
    elif sensor.validity == Validity.DEGRADED:
        peak_v = Validity.DEGRADED if peak_v == Validity.OK else peak_v
        peak_reasons.extend(sensor.reasons)
        peak_conf *= 0.7
    peak_conf = clip_confidence(peak_conf)

    path_v = traj.validity
    path_conf = fuse_confidence(traj.confidence, ahrs.confidence)
    path_reasons = list(traj.reasons)
    if strap.validity != Validity.OK:
        path_reasons.extend(strap.reasons)
        if strap.validity == Validity.ABSTAIN:
            path_v = Validity.ABSTAIN
            path_conf = clip_confidence(path_conf * 0.35)
        elif path_v == Validity.OK:
            path_v = Validity.DEGRADED

    plane_reasons: list[str] = []
    plane_ok = math.isfinite(plane_residual_rms) and plane_residual_rms < 0.08
    plane_v = Validity.OK if plane_ok else Validity.DEGRADED
    plane_conf = clip_confidence(0.75 if plane_ok else 0.45)
    if not plane_ok:
        plane_reasons.append("plane_residual_high")
    if path_v == Validity.ABSTAIN:
        plane_v = Validity.ABSTAIN
        plane_conf = clip_confidence(plane_conf * 0.3)
        plane_reasons.append("trajectory_unavailable")
    elif path_v == Validity.DEGRADED and plane_v == Validity.OK:
        plane_v = Validity.DEGRADED
        plane_reasons.append("trajectory_degraded")

    # Casting: wrist-release timing proxy — abstain when not observable.
    wrist_like = "hand" in channel_kind.lower() or "forearm" in channel_kind.lower() or "watch" in channel_kind.lower() or "glove" in channel_kind.lower()
    if casting_observability_ok is None:
        casting_observability_ok = bool(
            wrist_like
            and not bool(rigidity_fail)
            and impact.validity != Validity.ABSTAIN
            and traj.validity != Validity.ABSTAIN
            and strap.validity != Validity.ABSTAIN
            and sensor.validity != Validity.ABSTAIN
        )
    casting_reasons: list[str] = []
    if not casting_observability_ok:
        casting_v = Validity.ABSTAIN
        casting_conf = 0.1
        if bool(rigidity_fail):
            casting_reasons.append("casting_unobservable_rigidity_fail")
        if not wrist_like:
            casting_reasons.append("casting_unobservable_mount")
        if impact.validity == Validity.ABSTAIN:
            casting_reasons.append("casting_needs_impact")
        if traj.validity == Validity.ABSTAIN:
            casting_reasons.append("casting_needs_trajectory")
        if strap.validity == Validity.ABSTAIN:
            casting_reasons.append("casting_blocked_strap_slip")
        if sensor.validity == Validity.ABSTAIN:
            casting_reasons.append("casting_blocked_sensor")
        if not casting_reasons:
            casting_reasons.append("casting_observability_insufficient")
    else:
        casting_v = Validity.OK if impact.validity == Validity.OK else Validity.DEGRADED
        casting_conf = clip_confidence(0.7 * timing_conf)
        casting_reasons.append("casting_timing_proxy")
        if impact.validity == Validity.DEGRADED:
            casting_reasons.append("impact_kinematic_not_collision")

    return {
        "tempo": LayerQuality("tempo", timing_v, timing_conf, timing_reasons),
        "rhythm": LayerQuality("rhythm", timing_v, timing_conf, list(timing_reasons)),
        "transition": LayerQuality(
            "transition", timing_v, timing_conf, list(timing_reasons)
        ),
        "peak_omega": LayerQuality("peak_omega", peak_v, peak_conf, peak_reasons),
        "path": LayerQuality("path", path_v, path_conf, path_reasons),
        "plane": LayerQuality("plane", plane_v, plane_conf, plane_reasons),
        "casting": LayerQuality("casting", casting_v, casting_conf, casting_reasons),
    }


__all__ = [
    "IMPACT_PROVENANCE_ABSTAIN",
    "IMPACT_PROVENANCE_COLLISION",
    "IMPACT_PROVENANCE_KINEMATIC",
    "LayerQuality",
    "TruthQualityReport",
    "commercial_impact_provenance",
    "evaluate_ahrs_layer",
    "evaluate_impact_layer",
    "evaluate_sensor_layer",
    "evaluate_strap_slip_layer",
    "evaluate_trajectory_layer",
    "evaluate_truth_quality",
    "feature_quality_from_truth",
]
