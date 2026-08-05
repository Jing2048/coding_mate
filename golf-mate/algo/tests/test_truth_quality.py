"""Commercial truth-layer quality: impact provenance, traj honesty, strap slip, priors."""

from __future__ import annotations

import numpy as np

from golfmate_algo.bench.gates import check_gates
from golfmate_algo.bench.golden import scirep_budgets
from golfmate_algo.export.commercial_report import (
    build_commercial_report,
    export_commercial_report,
)
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.quality.orientation_uncertainty import estimate_orientation_uncertainty
from golfmate_algo.quality.truth_quality import (
    IMPACT_PROVENANCE_ABSTAIN,
    IMPACT_PROVENANCE_COLLISION,
    IMPACT_PROVENANCE_KINEMATIC,
    commercial_impact_provenance,
    evaluate_sensor_layer,
    evaluate_strap_slip_layer,
    evaluate_trajectory_layer,
    evaluate_truth_quality,
    feature_quality_from_truth,
)
from golfmate_algo.quality.uncertainty import Validity
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.traj.hybrid import estimate_hybrid_trajectory
from golfmate_algo.types import ImuPacket, SensorFrame, Handedness, WristSide


def test_impact_provenance_mapping():
    assert commercial_impact_provenance("collision") == IMPACT_PROVENANCE_COLLISION
    assert commercial_impact_provenance("kinematic_proxy") == IMPACT_PROVENANCE_KINEMATIC
    assert commercial_impact_provenance("kinematic") == IMPACT_PROVENANCE_KINEMATIC
    assert commercial_impact_provenance("unavailable") == IMPACT_PROVENANCE_ABSTAIN
    assert commercial_impact_provenance("abstain") == IMPACT_PROVENANCE_ABSTAIN
    assert commercial_impact_provenance("unknown") == IMPACT_PROVENANCE_ABSTAIN


def test_clean_swing_truth_quality_ok():
    syn = planar_circular_swing(fs_hz=200.0, casting=False)
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    tq = report.meta["truth_quality"]
    assert "layers" in tq
    for name in ("impact", "ahrs", "trajectory", "strap_slip", "sensor"):
        assert name in tq["layers"]
        assert tq["layers"][name]["validity"] in {"ok", "degraded", "abstain"}
    assert report.meta["impact_provenance"] in {
        IMPACT_PROVENANCE_COLLISION,
        IMPACT_PROVENANCE_KINEMATIC,
        IMPACT_PROVENANCE_ABSTAIN,
    }
    # Clean synth should not silently abstain trajectory.
    assert tq["layers"]["trajectory"]["validity"] != "abstain" or (
        "trajectory_unavailable" in tq["layers"]["trajectory"]["reasons"]
    )
    assert "orientation_uncertainty" in report.meta
    assert "summary" in report.meta["orientation_uncertainty"]
    assert "mean_deg" in report.meta["orientation_uncertainty"]["summary"]
    commercial = build_commercial_report(report)
    assert commercial.meta["impact_provenance"] == report.meta["impact_provenance"]
    assert commercial.meta.get("truth_quality") is not None
    assert commercial.meta.get("orientation_uncertainty") is not None


def test_kinematic_impact_never_claims_collision():
    # Low-rate stream forces kinematic / abstain path in segmental detector.
    syn = planar_circular_swing(fs_hz=50.0, casting=False)
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    provenance = report.meta["impact_provenance"]
    assert provenance in {IMPACT_PROVENANCE_KINEMATIC, IMPACT_PROVENANCE_ABSTAIN}
    assert provenance != IMPACT_PROVENANCE_COLLISION
    tq = report.meta["truth_quality"]
    impact = tq["layers"]["impact"]
    assert impact["validity"] in {Validity.DEGRADED.value, Validity.ABSTAIN.value}
    assert "collision" not in (impact.get("extras") or {}).get("impact_provenance", "")
    payload = export_commercial_report(report)
    assert payload["meta"]["impact_provenance"] == provenance
    tempo = next(m for m in payload["truth"] if m["name"] == "tempo_s")
    assert tempo["extras"]["impact_provenance"] == provenance
    assert tempo["validity"] != "ok" or provenance == IMPACT_PROVENANCE_COLLISION


def test_missing_impact_abstains_explicitly():
    tq = evaluate_truth_quality(
        impact_mode="unavailable",
        impact_confidence=0.1,
        radius_m=0.5,
        residual_rms=5.0,
        rank=3.0,
        fallback=0.0,
    )
    assert tq.impact_provenance == IMPACT_PROVENANCE_ABSTAIN
    assert tq.layers["impact"].validity == Validity.ABSTAIN
    assert "impact_unavailable" in tq.layers["impact"].reasons
    # Overall must not look cleaner than abstained impact.
    assert tq.overall_validity == Validity.ABSTAIN


def test_implausible_trajectory_abstains():
    layer = evaluate_trajectory_layer(
        radius_m=0.05,
        residual_rms=30.0,
        rank=1.0,
        fallback=1.0,
    )
    assert layer.validity == Validity.ABSTAIN
    assert "trajectory_unavailable" in layer.reasons or "lever_rank_low" in layer.reasons
    tq = evaluate_truth_quality(
        impact_mode="collision",
        radius_m=0.05,
        residual_rms=30.0,
        rank=1.0,
        fallback=1.0,
    )
    assert tq.layers["trajectory"].validity == Validity.ABSTAIN
    assert tq.overall_validity == Validity.ABSTAIN


def test_strap_slip_layer_and_hybrid_meta():
    syn = planar_circular_swing(fs_hz=200.0)
    dt = 1.0 / syn.packet.frame.fs_hz
    hy = estimate_hybrid_trajectory(
        syn.quats_true,
        syn.packet.gyro,
        syn.packet.accel,
        dt,
        syn.phases_true,
    )
    assert "strap_slip_score" in hy.meta
    assert "strap_slip_detected" in hy.meta
    # Clean analytic: should not trip strap slip.
    assert float(hy.meta["strap_slip_detected"]) < 0.5

    slip = evaluate_strap_slip_layer(
        strap_slip_score=0.8,
        strap_slip_detected=True,
        lever_angle_delta_deg=40.0,
        radius_ratio=1.8,
    )
    assert slip.validity == Validity.ABSTAIN
    assert "strap_slip_detected" in slip.reasons


def test_personal_lever_prior_applied_without_breaking_default():
    syn = planar_circular_swing(fs_hz=200.0, radius_m=0.55)
    dt = 1.0 / syn.packet.frame.fs_hz
    baseline = estimate_hybrid_trajectory(
        syn.quats_true,
        syn.packet.gyro,
        syn.packet.accel,
        dt,
        syn.phases_true,
    )
    prior = estimate_hybrid_trajectory(
        syn.quats_true,
        syn.packet.gyro,
        syn.packet.accel,
        dt,
        syn.phases_true,
        lever_prior_radius_m=0.55,
    )
    assert float(prior.meta.get("lever_prior_applied", 0.0)) == 1.0
    assert float(prior.meta.get("lever_prior_weight", 0.0)) > 0.0
    # Default path unchanged when prior omitted.
    assert float(baseline.meta.get("lever_prior_applied", 0.0)) == 0.0
    # Pipeline accepts prior kwargs.
    report = analyze_swing(
        syn.packet,
        prefer_vqf=False,
        compare_to_ideal=False,
        lever_prior_radius_m=0.55,
    )
    assert float(report.meta.get("lever_prior_applied", 0.0)) == 1.0


def test_saturation_degrades_sensor_layer():
    syn = planar_circular_swing(fs_hz=200.0)
    params = ImuErrorParams(
        gyro_range_deg_s=500.0,
        accel_range_g=4.0,
        seed=0,
    )
    t2, gyro2, accel2, _ = apply_imu_errors(
        syn.packet.t, syn.packet.gyro, syn.packet.accel, params
    )
    layer = evaluate_sensor_layer(gyro=gyro2, accel=accel2, t=t2)
    # Either degraded/abstain with saturation reason, or clean if swing stays in range.
    if layer.extras.get("saturation_frac", 0.0) >= 0.002:
        assert layer.validity in {Validity.DEGRADED, Validity.ABSTAIN}
        assert "sensor_saturation" in layer.reasons
    # Force saturation for a deterministic check.
    g_sat = syn.packet.gyro.copy()
    g_sat[10:30] = np.radians(2000.0)
    forced = evaluate_sensor_layer(
        gyro=g_sat,
        accel=syn.packet.accel,
        t=syn.packet.t,
        gyro_range_rad_s=np.radians(2000.0),
    )
    assert forced.validity in {Validity.DEGRADED, Validity.ABSTAIN}
    assert "sensor_saturation" in forced.reasons

    noisy_pkt = ImuPacket(
        frame=syn.packet.frame,
        t=t2,
        gyro=gyro2,
        accel=accel2,
    )
    report = analyze_swing(noisy_pkt, prefer_vqf=False, compare_to_ideal=False)
    assert "sensor" in report.meta["truth_quality"]["layers"]


def test_orientation_uncertainty_from_ahrs_evidence():
    n = 100
    gate = np.zeros(n)
    gate[:20] = 0.8
    innov = np.linspace(2.0, 20.0, n)
    bias = np.zeros((n, 3))
    bias[:, 0] = 0.02
    unc = estimate_orientation_uncertainty(
        gate=gate, bias=bias, innovation_deg=innov, n=n
    )
    assert unc.sigma_deg.shape == (n,)
    assert np.all(np.isfinite(unc.sigma_deg))
    assert unc.summary["p95_deg"] >= unc.summary["p50_deg"]
    # Closed-gate region should be higher uncertainty than open-gate address.
    assert float(np.mean(unc.sigma_deg[50:])) > float(np.mean(unc.sigma_deg[:20]))


def test_casting_abstains_when_observability_fails():
    tq = evaluate_truth_quality(
        impact_mode="unavailable",
        radius_m=0.4,
        residual_rms=5.0,
        rank=3.0,
        fallback=0.0,
        strap_slip_detected=False,
    )
    feats = feature_quality_from_truth(
        truth=tq,
        peak_omega_rad_s=10.0,
        plane_residual_rms=0.02,
        channel_kind="unknown_segment",
        rigidity_fail=True,
    )
    assert feats["casting"].validity == Validity.ABSTAIN
    assert any("casting" in r for r in feats["casting"].reasons)

    # Wrist-like mount with clean truth keeps casting as proxy (not abstain).
    tq_ok = evaluate_truth_quality(
        impact_mode="collision",
        impact_confidence=0.9,
        radius_m=0.5,
        residual_rms=4.0,
        rank=3.0,
        fallback=0.0,
    )
    feats_ok = feature_quality_from_truth(
        truth=tq_ok,
        peak_omega_rad_s=12.0,
        plane_residual_rms=0.02,
        channel_kind="forearm_segment",
        rigidity_fail=False,
    )
    assert feats_ok["casting"].validity in {Validity.OK, Validity.DEGRADED}
    assert feats_ok["tempo"].validity in {Validity.OK, Validity.DEGRADED}
    assert feats_ok["path"].validity in {Validity.OK, Validity.DEGRADED}


def test_commercial_feature_quality_p0_keys():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=False, compare_to_ideal=False)
    fq = report.meta["feature_quality"]
    for key in ("tempo", "rhythm", "transition", "peak_omega", "path", "plane", "casting"):
        assert key in fq
        assert fq[key]["validity"] in {"ok", "degraded", "abstain"}


def test_aspirational_gates_do_not_fail_ci_when_position_slightly_above_12():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer_wrist": {"mean": 5.0}}},
                "e2e": {
                    "consumer_wrist": {
                        "position_cm": {"mean": 12.02},
                        "orientation_deg": {"mean": 2.2},
                    }
                },
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "violation_stress": {
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 10.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.05}},
                },
            },
            "external_multisense": {"status": "unavailable", "reason": "test"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 6.0}},
            "gyro_only": {"consumer": {"mean": 50.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = check_gates(payload)
    assert g["pass"] is True  # hard product position budget remains 17 cm
    asp = g["aspirational"]
    assert asp["budgets"]["position_cm"] == scirep_budgets.ASPIRATIONAL_POSITION_CM
    assert asp["status"]["impact_ms"]["pass"] is True
    assert asp["status"]["orientation_deg"]["pass"] is True
    assert asp["status"]["position_cm"]["pass"] is False
    assert asp["pass"] is False
    assert any("aspirational" in n for n in g["notes"])


def test_product_gates_use_tightened_impact_and_orientation():
    assert scirep_budgets.PRODUCT_IMPACT_MS == 15.0
    assert scirep_budgets.PRODUCT_ORIENTATION_DEG == 6.0
    assert scirep_budgets.PRODUCT_POSITION_CM == 17.0
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 16.0}}},
                "e2e": {
                    "consumer": {
                        "position_cm": {"mean": 10.0},
                        "orientation_deg": {"mean": 2.0},
                    }
                },
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "violation_stress": {
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 10.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.05}},
                },
            },
            "external_multisense": {"status": "unavailable", "reason": "test"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 6.0}},
            "gyro_only": {"consumer": {"mean": 50.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = check_gates(payload)
    assert g["pass"] is False
    assert any("15 ms" in v for v in g["violations"])


def test_synthetic_strap_slip_detection_on_rotated_late_lever():
    """Force early/late lever inconsistency via mid-swing body-frame rotation of accel."""
    syn = planar_circular_swing(fs_hz=200.0, radius_m=0.5)
    pkt = syn.packet
    n = pkt.gyro.shape[0]
    mid = n // 2
    # Rotate measured accel in the second half to mimic strap reorientation.
    ang = np.radians(35.0)
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    accel2 = pkt.accel.copy()
    accel2[mid:] = accel2[mid:] @ R.T
    gyro2 = pkt.gyro.copy()
    gyro2[mid:] = gyro2[mid:] @ R.T
    slipped = ImuPacket(
        frame=SensorFrame(
            fs_hz=pkt.frame.fs_hz,
            wrist=WristSide.LEAD,
            handedness=Handedness.RIGHT,
            device_id="watch_test",
            is_canonical=True,
        ),
        t=pkt.t.copy(),
        gyro=gyro2,
        accel=accel2,
    )
    dt = 1.0 / slipped.frame.fs_hz
    # Use true phases/quats so the detector sees lever inconsistency, not AHRS fail.
    hy = estimate_hybrid_trajectory(
        syn.quats_true, slipped.gyro, slipped.accel, dt, syn.phases_true
    )
    # Detector should elevate score relative to clean baseline.
    clean = estimate_hybrid_trajectory(
        syn.quats_true, pkt.gyro, pkt.accel, dt, syn.phases_true
    )
    assert float(hy.meta["strap_slip_score"]) >= float(clean.meta["strap_slip_score"])
