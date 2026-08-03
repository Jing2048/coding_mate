"""Tests for ideal reference scoring and Core ML feature export contract."""

from __future__ import annotations

from golfmate_algo.export import CONTRACT_VERSION, export_feature_vector, load_schema
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.reference.ideal_kinematics import fit_ideal_template, load_ideal_template
from golfmate_algo.reference.score import score_against_reference
from golfmate_algo.synth.analytic import planar_circular_swing


def test_ideal_template_prefers_healthy_over_casting():
    tmpl = load_ideal_template()
    healthy = analyze_swing(planar_circular_swing(casting=False).packet, use_crop_lite=False)
    casting = analyze_swing(planar_circular_swing(casting=True, casting_lead_s=0.12).packet, use_crop_lite=False)
    sh = score_against_reference(healthy, tmpl)
    sc = score_against_reference(casting, tmpl)
    assert sh.is_proxy and sc.is_proxy
    # Casting early-release should reduce peak_omega_to_impact band score
    assert sc.per_feature["peak_omega_to_impact_s"] <= sh.per_feature["peak_omega_to_impact_s"] + 1e-9


def test_pipeline_embeds_reference_finding():
    report = analyze_swing(planar_circular_swing().packet, use_crop_lite=False)
    codes = {f.code for f in report.findings}
    assert any(c.startswith("reference_") for c in codes)
    assert "reference_score" in report.meta
    assert report.meta["reference_score"]["is_proxy"] is True


def test_feature_export_contract_stable():
    report = analyze_swing(planar_circular_swing().packet, use_crop_lite=False)
    vec = export_feature_vector(report)
    schema = load_schema()
    assert vec.version == CONTRACT_VERSION == schema["contract_version"]
    assert list(vec.names) == schema["features"]
    assert vec.values.shape == (len(schema["features"]),)
    d = vec.as_dict()
    assert d["version"] == CONTRACT_VERSION
