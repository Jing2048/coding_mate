"""CommercialSwingReport v2 contract + high-order finding label semantics."""

from __future__ import annotations

import json

import pytest

from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.export.commercial_report import (
    CONTRACT_VERSION,
    INFERENCE_METRIC_NAMES,
    PERSONAL_BASELINE_VERSION,
    PRACTICE_LOOP_VERSION,
    STRATEGY_VERSION,
    TRUTH_METRIC_NAMES,
    build_commercial_report,
    export_commercial_report,
    load_commercial_schema,
    validate_commercial_report_dict,
)
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.quality.uncertainty import (
    REQUIRED_METRIC_KEYS,
    MetricEstimate,
    MetricKind,
    Validity,
    validate_metric_dict,
)
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.types import DiagnosticFinding, WristFeatures


def _base_features(**overrides: float) -> WristFeatures:
    base = dict(
        tempo_s=1.0,
        backswing_s=0.75,
        downswing_s=0.25,
        rhythm=3.0,
        peak_omega_rad_s=10.0,
        peak_omega_idx=100,
        peak_omega_to_impact_s=0.02,
        hand_speed_peak_m_s=5.0,
        plane_angle_deg=50.0,
        closure_rate_rad_s=1.0,
    )
    base.update(overrides)
    return WristFeatures(**base)


def test_metric_estimate_requires_residual_and_serializes_enums():
    m = MetricEstimate(
        name="tempo_s",
        value=1.2,
        units="s",
        kind=MetricKind.DERIVED,
        confidence=0.8,
        validity=Validity.OK,
        residual=0.01,
    )
    d = m.as_dict()
    for key in REQUIRED_METRIC_KEYS:
        assert key in d
    assert d["kind"] == "derived"
    assert d["validity"] == "ok"
    validate_metric_dict(d)


def test_validate_metric_dict_rejects_bad_kind():
    with pytest.raises(ValueError, match="kind"):
        validate_metric_dict(
            {
                "name": "x",
                "value": 1.0,
                "units": "s",
                "kind": "measured_truth",
                "validity": "ok",
                "confidence": 0.5,
                "residual": 0.0,
            }
        )


def test_high_order_findings_never_claim_measured():
    feats = _base_features()
    high_order = {
        "kind": "inferred",
        "confidence": 0.7,
        "residual": 0.2,
        "wrist": {
            "fe_impact_deg": 12.0,
            "fe_delta_address_to_impact_deg": -8.0,
        },
        "club": {"face_open_closed": "open", "face_impact_deg": 6.0},
        "body": {
            "sequence_order_ok": False,
            "pelvis_peak_to_impact_s": 0.12,
            "club_peak_to_impact_s": 0.01,
        },
    }
    findings = diagnose(feats, high_order=high_order)
    inferred = [f for f in findings if f.kind == "inferred"]
    assert inferred, "expected high-order inferred findings"
    codes = {f.code for f in inferred}
    assert "wrist_extends_into_impact" in codes
    assert "clubface_open_impact" in codes
    assert "kinematic_sequence_out_of_order" in codes
    for f in inferred:
        assert f.is_proxy is True
        assert f.kind == "inferred"


def test_commercial_schema_matches_constants():
    schema = load_commercial_schema()
    assert schema["contract_version"] == CONTRACT_VERSION
    assert schema["sections"]["truth"]["metric_names"] == list(TRUTH_METRIC_NAMES)
    assert set(schema["sections"]["inference"]["metric_names"]) == set(
        INFERENCE_METRIC_NAMES
    )
    assert schema["sections"]["practice_loop"]["version"] == PRACTICE_LOOP_VERSION
    assert schema["sections"]["strategy"]["version"] == STRATEGY_VERSION
    assert schema["sections"]["personal_baseline"]["version"] == PERSONAL_BASELINE_VERSION
    assert schema["required_metric_keys"] == list(REQUIRED_METRIC_KEYS)


def test_export_commercial_report_from_pipeline():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    commercial = build_commercial_report(report)
    assert commercial.version == CONTRACT_VERSION
    assert [m.name for m in commercial.truth] == list(TRUTH_METRIC_NAMES)
    for m in commercial.all_metrics():
        validate_metric_dict(m.as_dict())
        assert m.kind in MetricKind
        assert m.validity in Validity

    payload = export_commercial_report(report)
    validate_commercial_report_dict(payload)
    assert payload["personal_baseline"]["implemented"] is False
    assert payload["practice_loop"]["implemented"] is False
    assert payload["strategy"]["implemented"] is False
    assert payload["practice_loop"]["version"] == PRACTICE_LOOP_VERSION
    assert payload["strategy"]["version"] == STRATEGY_VERSION

    wire = json.loads(json.dumps(payload, allow_nan=False))
    assert wire["version"] == CONTRACT_VERSION


def test_abstained_metrics_are_strict_json_null_not_nan():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    report.meta["high_order"] = None
    payload = export_commercial_report(report)
    abstained = [m for m in payload["inference"] if m["validity"] == "abstain"]
    assert abstained
    assert all(m["value"] is None for m in abstained)
    json.dumps(payload, allow_nan=False)


def test_nonfinite_available_metric_is_forced_to_abstain():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    report.features.extras.pop("x_factor_proxy_deg", None)
    report.meta["biomech_proxies"] = {}
    payload = export_commercial_report(report)
    metric = next(m for m in payload["inference"] if m["name"] == "x_factor_proxy_deg")
    assert metric["validity"] == "abstain"
    assert metric["value"] is None
    assert "value_unavailable" in metric["reasons"]
    validate_commercial_report_dict(payload)


def test_commercial_report_preserves_swing_report():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    before = {
        "tempo": report.features.tempo_s,
        "n_findings": len(report.findings),
        "meta_keys": set(report.meta.keys()),
    }
    _ = export_commercial_report(report)
    assert report.features.tempo_s == before["tempo"]
    assert len(report.findings) == before["n_findings"]
    assert set(report.meta.keys()) == before["meta_keys"]


def test_inference_metrics_are_never_measured():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    payload = export_commercial_report(report)
    for m in payload["inference"]:
        assert m["kind"] in {"proxy", "inferred"}
        assert m["kind"] != "measured"


def test_inferred_finding_validator_rejects_is_proxy_false():
    bad = {
        "version": CONTRACT_VERSION,
        "truth": [
            MetricEstimate(
                name="tempo_s",
                value=1.0,
                units="s",
                kind=MetricKind.DERIVED,
                confidence=0.8,
                validity=Validity.OK,
            ).as_dict()
        ],
        "inference": [
            MetricEstimate(
                name="casting_onset_s",
                value=0.02,
                units="s",
                kind=MetricKind.PROXY,
                confidence=0.7,
                validity=Validity.OK,
            ).as_dict()
        ],
        "personal_baseline": {
            "version": PERSONAL_BASELINE_VERSION,
            "implemented": False,
            "deltas": [],
            "meta": {},
        },
        "practice_loop": {
            "version": PRACTICE_LOOP_VERSION,
            "implemented": False,
            "focus_kpi": None,
            "in_window": None,
            "correction_direction": None,
            "session_consistency": None,
            "metrics": [],
            "meta": {},
        },
        "strategy": {
            "version": STRATEGY_VERSION,
            "implemented": False,
            "tempo_under_pressure": None,
            "dispersion": None,
            "miss_bias": None,
            "consistency_decay": None,
            "metrics": [],
            "meta": {},
        },
        "findings": [
            {
                "code": "clubface_open_impact",
                "severity": "warn",
                "message": "bad",
                "evidence": {},
                "is_proxy": False,
                "kind": "inferred",
            }
        ],
        "phases": {},
        "meta": {},
    }
    with pytest.raises(ValueError, match="is_proxy"):
        validate_commercial_report_dict(bad)


def test_diagnostic_finding_default_kind_proxy():
    f = DiagnosticFinding(code="rhythm_ok", severity="info", message="ok")
    assert f.is_proxy is True
    assert f.kind == "proxy"
