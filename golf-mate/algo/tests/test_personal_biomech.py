"""Personal biomech prior, practice-loop, and strategy feature tests."""

from __future__ import annotations

import json
import math
from copy import deepcopy

import pytest

from golfmate_algo.export.commercial_report import (
    build_commercial_report,
    export_commercial_report,
    load_commercial_schema,
    validate_commercial_report_dict,
)
from golfmate_algo.personal_biomech import (
    CORE_PRIOR_METRICS,
    PERSONAL_BASELINE_VERSION,
    PRACTICE_LOOP_VERSION,
    STRATEGY_VERSION,
    PersonalBiomechPrior,
    PracticeCue,
    SwingContext,
    build_practice_loop_features,
    build_strategy_features,
    cue_for_metric,
    fit_personal_prior,
    score_against_prior,
)
from golfmate_algo.personal_biomech.practice import select_focus_metric
from golfmate_algo.personal_biomech.prior import load_personal_baseline_schema
from golfmate_algo.personal_biomech.practice import load_practice_loop_schema
from golfmate_algo.personal_biomech.strategy import load_strategy_schema
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.quality.uncertainty import MetricEstimate, MetricKind, Validity
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.types import SwingPhases, SwingReport, WristFeatures


def _features(**overrides: float) -> WristFeatures:
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


def _phases() -> SwingPhases:
    return SwingPhases(address_idx=0, top_idx=40, impact_idx=60, finish_idx=90)


def _synthetic_report(**feature_overrides: float) -> SwingReport:
    import numpy as np

    feats = _features(**feature_overrides)
    return SwingReport(
        phases=_phases(),
        features=feats,
        findings=[],
        quats=np.zeros((100, 4)),
        positions=np.zeros((100, 3)),
        velocities=np.zeros((100, 3)),
        gate_open=np.ones(100),
        meta={
            "radius_m": 0.55,
            "feature_quality": {
                "tempo": {"validity": "ok", "confidence": 0.85, "reasons": []},
                "peak_omega": {"validity": "ok", "confidence": 0.9, "reasons": []},
                "plane": {"validity": "ok", "confidence": 0.7, "reasons": []},
                "path": {"validity": "ok", "confidence": 0.7, "reasons": []},
            },
        },
    )


def _metric_map_report(
    values: dict[str, float],
    *,
    validity: str = "ok",
    confidence: float = 0.8,
) -> dict[str, MetricEstimate]:
    units = {
        "tempo_s": "s",
        "rhythm": "1",
        "peak_omega_to_impact_s": "s",
        "peak_omega_rad_s": "rad/s",
        "plane_angle_deg": "deg",
        "hand_speed_peak_m_s": "m/s",
        "trajectory_radius_m": "m",
    }
    return {
        name: MetricEstimate(
            name=name,
            value=float(val),
            units=units[name],
            kind=MetricKind.DERIVED,
            confidence=confidence,
            validity=Validity(validity),
        )
        for name, val in values.items()
    }


class _FakeCommercial:
    def __init__(self, metrics: dict[str, MetricEstimate]):
        self.truth = list(metrics.values())
        self.inference = []


def _baseline_values(seed: int = 0) -> dict[str, float]:
    # Deterministic personal center near typical amateur band.
    return {
        "tempo_s": 1.00 + 0.01 * (seed % 3),
        "rhythm": 3.0 + 0.05 * ((seed // 3) % 2),
        "peak_omega_to_impact_s": 0.02,
        "peak_omega_rad_s": 10.0 + 0.1 * (seed % 2),
        "plane_angle_deg": 50.0 + 0.5 * (seed % 2),
        "hand_speed_peak_m_s": 5.0,
        "trajectory_radius_m": 0.55,
    }


def _make_fit_reports(n: int = 8, *, outlier_at: int | None = None) -> list[SwingReport]:
    reports: list[SwingReport] = []
    for i in range(n):
        vals = _baseline_values(i)
        if outlier_at is not None and i == outlier_at:
            vals["tempo_s"] = 4.5  # extreme outlier
            vals["rhythm"] = 12.0
        reports.append(_synthetic_report(**{k: v for k, v in vals.items() if k != "trajectory_radius_m"}))
        reports[-1].meta["radius_m"] = vals["trajectory_radius_m"]
    return reports


def test_schemas_versioned_and_loadable():
    pb = load_personal_baseline_schema()
    pl = load_practice_loop_schema()
    st = load_strategy_schema()
    assert pb["version"] == PERSONAL_BASELINE_VERSION
    assert pl["version"] == PRACTICE_LOOP_VERSION
    assert st["version"] == STRATEGY_VERSION
    assert pb["core_metrics"] == list(CORE_PRIOR_METRICS)
    assert st["rules"]["not_strokes_gained"] is True
    commercial = load_commercial_schema()
    assert commercial["sections"]["personal_baseline"]["version"] == PERSONAL_BASELINE_VERSION


def test_robust_outlier_handling_does_not_contaminate_center():
    clean = _make_fit_reports(10)
    prior_clean = fit_personal_prior(clean, min_samples=5, min_coverage=0.4)
    contaminated = _make_fit_reports(10, outlier_at=0)
    prior_bad = fit_personal_prior(contaminated, min_samples=5, min_coverage=0.4)

    tempo_clean = prior_clean.metrics["tempo_s"]
    tempo_bad = prior_bad.metrics["tempo_s"]
    assert tempo_clean.validity in (Validity.OK, Validity.DEGRADED)
    assert tempo_bad.validity in (Validity.OK, Validity.DEGRADED)
    # Outlier must not pull center toward 4.5
    assert abs(tempo_bad.center - tempo_clean.center) < 0.15
    assert tempo_bad.center < 1.5
    assert "outliers_rejected" in tempo_bad.reasons


def test_min_sample_abstain():
    reports = _make_fit_reports(3)
    prior = fit_personal_prior(reports, min_samples=5, min_coverage=0.4)
    for name in CORE_PRIOR_METRICS:
        m = prior.metrics[name]
        assert m.validity == Validity.ABSTAIN
        assert "min_samples_not_met" in m.reasons


def test_abstained_observation_does_not_enter_fit():
    reports = _make_fit_reports(8)
    # Force one swing's tempo to abstain via feature_quality.
    reports[0].meta["feature_quality"]["tempo"] = {
        "validity": "abstain",
        "confidence": 0.1,
        "reasons": ["impact_unavailable"],
    }
    reports[0].features.tempo_s = 9.0  # would poison median if included
    prior = fit_personal_prior(reports, min_samples=5, min_coverage=0.3)
    assert prior.metrics["tempo_s"].center < 2.0
    assert prior.metrics["tempo_s"].n_samples <= 7


def test_signed_direction_vs_personal_baseline():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    center = prior.metrics["tempo_s"].center
    fast = _synthetic_report(tempo_s=center + 0.25)
    slow = _synthetic_report(tempo_s=center - 0.25)
    s_fast = score_against_prior(fast, prior)
    s_slow = score_against_prior(slow, prior)
    assert s_fast.scores["tempo_s"].signed_error > 0
    assert s_slow.scores["tempo_s"].signed_error < 0
    assert s_fast.scores["tempo_s"].baseline == "personal"
    assert s_fast.scores["tempo_s"].validity in (Validity.OK, Validity.DEGRADED)


def test_personal_preferred_over_tour():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    # Personal tempo center ~1.0; tour ideal ~0.68 — scoring must use personal.
    swing = _synthetic_report(tempo_s=1.05)
    scored = score_against_prior(swing, prior)
    assert scored.scores["tempo_s"].baseline == "personal"
    # Error should be small vs personal, not ~0.37 vs tour.
    assert abs(scored.scores["tempo_s"].signed_error) < 0.2


def test_focus_selection_explicit_and_auto_worst_z():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    # Make rhythm the worst reliable deviation.
    swing = _synthetic_report(rhythm=prior.metrics["rhythm"].center + 3.0 * prior.metrics["rhythm"].scale)
    scored = score_against_prior(swing, prior)
    focus_auto, reasons = select_focus_metric(scored)
    assert focus_auto == "rhythm"
    assert "auto_worst_reliable_z" in reasons

    focus_explicit, reasons_e = select_focus_metric(scored, explicit="tempo_s")
    assert focus_explicit == "tempo_s"
    assert "explicit_focus" in reasons_e

    pl = build_practice_loop_features(swing, prior, focus_metric=None)
    assert pl.focus_metric == "rhythm"
    assert pl.error_sign == 1.0
    assert pl.correction_direction == -1.0
    assert pl.suggested_cue == PracticeCue.RHYTHM_SMOOTH_TRANSITION.value
    assert pl.in_window is False


def test_cue_hold_current_when_in_window():
    assert cue_for_metric("tempo_s", signed_error=0.01, in_window=True) == PracticeCue.HOLD_CURRENT
    # tempo_s is duration: +error = slower → speed up; -error = faster → slow down
    assert cue_for_metric("tempo_s", signed_error=0.2, in_window=False) == PracticeCue.TEMPO_SPEED_UP
    assert cue_for_metric("tempo_s", signed_error=-0.2, in_window=False) == PracticeCue.TEMPO_SLOW_DOWN


def test_cue_directions_match_physical_semantics():
    """Audit cue map: high signed_error = observed > baseline."""
    # Rhythm high → long backswing vs DS → smooth; low → rushed → lengthen BS
    assert cue_for_metric("rhythm", signed_error=1.0, in_window=False) == PracticeCue.RHYTHM_SMOOTH_TRANSITION
    assert cue_for_metric("rhythm", signed_error=-1.0, in_window=False) == PracticeCue.RHYTHM_LENGTHEN_BACKSWING
    # peak_omega_to_impact high → early release → delay; low → earlier
    assert cue_for_metric("peak_omega_to_impact_s", signed_error=0.05, in_window=False) == PracticeCue.RELEASE_DELAY
    assert cue_for_metric("peak_omega_to_impact_s", signed_error=-0.05, in_window=False) == PracticeCue.RELEASE_EARLIER
    # peak omega high → ease; low → build
    assert cue_for_metric("peak_omega_rad_s", signed_error=2.0, in_window=False) == PracticeCue.PEAK_OMEGA_EASE
    assert cue_for_metric("peak_omega_rad_s", signed_error=-2.0, in_window=False) == PracticeCue.PEAK_OMEGA_BUILD
    # plane_angle high = steeper → flatten; low = flatter → steepen
    assert cue_for_metric("plane_angle_deg", signed_error=5.0, in_window=False) == PracticeCue.PLANE_FLATTEN
    assert cue_for_metric("plane_angle_deg", signed_error=-5.0, in_window=False) == PracticeCue.PLANE_STEEPEN


def test_practice_tempo_cue_and_correction_direction():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    center = prior.metrics["tempo_s"].center
    slow = _synthetic_report(tempo_s=center + 3.0 * prior.metrics["tempo_s"].scale)
    pl = build_practice_loop_features(slow, prior, focus_metric="tempo_s")
    assert pl.focus_metric == "tempo_s"
    assert pl.error_sign == 1.0
    assert pl.correction_direction == -1.0  # opposite signed error
    assert pl.suggested_cue == PracticeCue.TEMPO_SPEED_UP.value

    fast = _synthetic_report(tempo_s=center - 3.0 * prior.metrics["tempo_s"].scale)
    pl_fast = build_practice_loop_features(fast, prior, focus_metric="tempo_s")
    assert pl_fast.error_sign == -1.0
    assert pl_fast.correction_direction == 1.0
    assert pl_fast.suggested_cue == PracticeCue.TEMPO_SLOW_DOWN.value


def test_pressure_comparison_and_missing_miss_context_abstain():
    reports = []
    contexts = []
    for i in range(6):
        tempo = 1.0 if i % 2 == 0 else 1.2
        reports.append(_synthetic_report(tempo_s=tempo))
        contexts.append(
            SwingContext(
                setting="round" if i % 2 else "practice",
                pressure=(i % 2 == 1),
                club_id="7i",
            )
        )
    # No miss context → miss_bias abstains
    features = build_strategy_features(reports, contexts)
    assert features.implemented is True
    assert features.tempo_under_pressure is not None
    assert features.tempo_under_pressure == pytest.approx(0.2, abs=0.05)
    assert features.miss_bias is None
    assert any("miss_bias_abstain" in r for r in features.reasons)
    miss_metric = next(m for m in features.metrics if m.name == "miss_bias")
    assert miss_metric.validity == Validity.ABSTAIN
    assert features.meta.get("club_stratified") is True
    assert "7i" in features.meta["by_club"]["tempo_under_pressure"]

    # With miss context → miss_bias populated
    contexts_miss = [
        SwingContext(setting="round", pressure=False, miss_direction=-1.0, outcome="left")
        for _ in reports
    ]
    features2 = build_strategy_features(reports, contexts_miss)
    assert features2.miss_bias == pytest.approx(-1.0)
    assert features2.tempo_under_pressure is None  # no pressure cohort
    assert features2.meta.get("club_context_missing") is True
    assert "club_context_missing" in features2.reasons
    # Aggregate without club IDs is degraded, not silently ok.
    miss_m = next(m for m in features2.metrics if m.name == "miss_bias")
    assert miss_m.validity == Validity.DEGRADED


def test_club_stratified_pressure_ignores_cross_club_mix():
    """Global mix suggests pressure delta; within-club deltas are zero → ~0."""
    reports: list[SwingReport] = []
    contexts: list[SwingContext] = []
    # Driver: calm + pressure both at 1.0 (within-club delta 0)
    # Many calm driver, few pressure driver
    for _ in range(5):
        reports.append(_synthetic_report(tempo_s=1.0))
        contexts.append(SwingContext(setting="practice", pressure=False, club_id="driver"))
    for _ in range(1):
        reports.append(_synthetic_report(tempo_s=1.0))
        contexts.append(SwingContext(setting="round", pressure=True, club_id="driver"))
    # 7i: calm + pressure both at 1.4 (within-club delta 0)
    # Few calm 7i, many pressure 7i → naive global pressure≈1.4, calm≈1.0
    for _ in range(1):
        reports.append(_synthetic_report(tempo_s=1.4))
        contexts.append(SwingContext(setting="practice", pressure=False, club_id="7i"))
    for _ in range(5):
        reports.append(_synthetic_report(tempo_s=1.4))
        contexts.append(SwingContext(setting="round", pressure=True, club_id="7i"))

    features = build_strategy_features(reports, contexts)
    by_club = features.meta["by_club"]["tempo_under_pressure"]
    assert by_club["driver"]["delta"] == pytest.approx(0.0, abs=1e-9)
    assert by_club["7i"]["delta"] == pytest.approx(0.0, abs=1e-9)
    assert features.tempo_under_pressure == pytest.approx(0.0, abs=1e-9)
    assert any("club_stratified" in r for r in features.reasons)


def test_by_club_miss_bias_summary():
    reports = [_synthetic_report() for _ in range(6)]
    contexts = [
        SwingContext(setting="round", pressure=False, club_id="driver", miss_direction=-1.0, outcome="left"),
        SwingContext(setting="round", pressure=False, club_id="driver", miss_direction=-1.0, outcome="left"),
        SwingContext(setting="round", pressure=False, club_id="driver", miss_direction=-0.8, outcome="left"),
        SwingContext(setting="round", pressure=False, club_id="7i", miss_direction=1.0, outcome="right"),
        SwingContext(setting="round", pressure=False, club_id="7i", miss_direction=1.0, outcome="right"),
        SwingContext(setting="round", pressure=False, club_id="7i", miss_direction=1.2, outcome="right"),
    ]
    features = build_strategy_features(reports, contexts)
    by_club = features.meta["by_club"]["miss_bias"]
    assert by_club["driver"]["miss_bias"] == pytest.approx(-1.0, abs=0.1)
    assert by_club["7i"]["miss_bias"] == pytest.approx(1.0, abs=0.1)
    # Aggregate is median of club medians ≈ 0
    assert features.miss_bias == pytest.approx(0.0, abs=0.15)
    miss_m = next(m for m in features.metrics if m.name == "miss_bias")
    assert miss_m.validity == Validity.OK
    assert "by_club" in miss_m.extras


def test_dispersion_is_biomech_z_not_ball():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    contexts = [
        SwingContext(setting="practice", pressure=False, club_id="7i") for _ in reports
    ]
    features = build_strategy_features(reports, contexts, prior=prior)
    assert features.meta["dispersion_kind"] == "biomechanics_z_dispersion"
    assert features.meta["dispersion_canonical_name"] == "biomech_z_dispersion"
    assert any("dispersion_is_biomech_z_not_ball" in r for r in features.reasons)
    canon = next(m for m in features.metrics if m.name == "biomech_z_dispersion")
    alias = next(m for m in features.metrics if m.name == "dispersion")
    assert canon.extras.get("not_ball_dispersion") is True
    assert alias.extras.get("canonical_name") == "biomech_z_dispersion"
    schema = load_strategy_schema()
    assert schema["dispersion"]["not_ball_dispersion"] is True
    assert "NOT ball" in schema["rules"]["dispersion"] or "not ball" in schema["rules"]["dispersion"].lower()


def test_no_club_id_all_cohort_degraded():
    reports = []
    contexts = []
    for i in range(6):
        tempo = 1.0 if i % 2 == 0 else 1.15
        reports.append(_synthetic_report(tempo_s=tempo))
        contexts.append(SwingContext(setting="practice", pressure=(i % 2 == 1)))
    features = build_strategy_features(reports, contexts)
    assert features.meta["club_context_missing"] is True
    assert "all" in features.meta["by_club"]["tempo_under_pressure"]
    assert features.meta["by_club"]["tempo_under_pressure"]["all"]["reason"] == "club_context_missing"
    tempo_m = next(m for m in features.metrics if m.name == "tempo_under_pressure")
    assert tempo_m.validity == Validity.DEGRADED
    assert "club_context_missing" in tempo_m.reasons


def test_serialization_determinism_and_strict_json():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    a = prior.to_json()
    b = prior.to_json()
    assert a == b
    restored = PersonalBiomechPrior.from_json(a)
    assert restored.to_json() == a
    json.loads(a)  # already allow_nan=False
    payload = json.loads(a)
    assert payload["version"] == PERSONAL_BASELINE_VERSION
    # No NaN literals in serialized usable metrics
    wire = json.dumps(payload, allow_nan=False)
    assert "NaN" not in wire


def test_commercial_report_wiring_placeholders_and_engine():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)

    # Old call behaviour: placeholders
    payload = export_commercial_report(report)
    validate_commercial_report_dict(payload)
    assert payload["personal_baseline"]["implemented"] is False
    assert payload["practice_loop"]["implemented"] is False
    assert payload["strategy"]["implemented"] is False
    json.dumps(payload, allow_nan=False)

    # With prior: personal + practice implemented
    fit_reports = _make_fit_reports(8)
    prior = fit_personal_prior(fit_reports, min_samples=5)
    commercial = build_commercial_report(report, prior=prior)
    assert commercial.personal_baseline.implemented is True
    assert commercial.practice_loop.implemented is True
    assert commercial.strategy.implemented is False
    assert commercial.practice_loop.focus_kpi is not None or commercial.practice_loop.suggested_cue == "abstain"
    payload2 = commercial.as_dict()
    validate_commercial_report_dict(payload2)
    json.dumps(payload2, allow_nan=False)

    # Strategy wiring
    contexts = [
        SwingContext(setting="practice", pressure=False, miss_direction=0.5, outcome="right")
        for _ in fit_reports
    ]
    commercial3 = build_commercial_report(
        report,
        prior=prior,
        strategy_reports=fit_reports,
        strategy_contexts=contexts,
    )
    assert commercial3.strategy.implemented is True
    assert commercial3.strategy.miss_bias is not None
    assert commercial3.strategy.meta.get("not_strokes_gained") is True
    validate_commercial_report_dict(commercial3.as_dict())


def test_face_metric_excluded_unless_calibrated():
    base_metrics = _metric_map_report(_baseline_values())
    face = MetricEstimate(
        name="clubface_impact_deg",
        value=4.0,
        units="deg",
        kind=MetricKind.INFERRED,
        confidence=0.7,
        validity=Validity.OK,
        reasons=["high_order_pcr"],
        extras={"head": "club", "face_calibrated": False},
    )
    fake_reports = [_FakeCommercial(deepcopy(base_metrics)) for _ in range(8)]
    for fr in fake_reports:
        fr.inference = [face]
    prior = fit_personal_prior(fake_reports, min_samples=5, include_face_if_calibrated=True)
    assert "clubface_impact_deg" not in prior.metrics

    fake_cal = []
    for i in range(8):
        m = _metric_map_report(_baseline_values(i))
        fr = _FakeCommercial(m)
        fr.inference = [
            MetricEstimate(
                name="clubface_impact_deg",
                value=3.0 + 0.05 * i,
                units="deg",
                kind=MetricKind.INFERRED,
                confidence=0.75,
                validity=Validity.OK,
                reasons=["calib_mae_within_ok_budget"],
                extras={"head": "club", "face_calibrated": True, "calibrated": True},
            )
        ]
        fake_cal.append(fr)
    prior_cal = fit_personal_prior(fake_cal, min_samples=5, include_face_if_calibrated=True)
    assert prior_cal.metrics["clubface_impact_deg"].validity in (Validity.OK, Validity.DEGRADED)
    assert math.isfinite(prior_cal.metrics["clubface_impact_deg"].center)


def test_all_metric_outputs_labeled():
    reports = _make_fit_reports(8)
    prior = fit_personal_prior(reports, min_samples=5)
    swing = _synthetic_report(tempo_s=1.3)
    scored = score_against_prior(swing, prior)
    for s in scored.deltas():
        d = s.as_dict()
        assert d["kind"] in {k.value for k in MetricKind}
        assert d["validity"] in {v.value for v in Validity}
        assert 0.0 <= d["confidence"] <= 1.0
        assert "residual" in d

    pl = build_practice_loop_features(swing, prior)
    for m in pl.metrics:
        assert m.name
        assert m.kind in MetricKind
        assert m.validity in Validity

    sf = build_strategy_features(
        reports,
        [SwingContext(setting="practice", pressure=False) for _ in reports],
        prior=prior,
    )
    for m in sf.metrics:
        d = m.as_dict()
        assert d["validity"] in {"ok", "degraded", "abstain"}
        json.dumps(d, allow_nan=False)
