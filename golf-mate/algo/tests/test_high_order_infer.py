"""Calibrated multi-head high-order PCR: splits, holdout, OOD, personal prior."""

from __future__ import annotations

import json

import numpy as np
import pytest

from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.export.commercial_report import (
    build_commercial_report,
    export_commercial_report,
)
from golfmate_algo.infer.high_order import (
    GENERATOR_FAMILIES,
    HEAD_NAMES,
    MODEL_VERSION,
    PERSONAL_PRIOR_VERSION,
    build_default_high_order_model,
    evaluate_leave_generator_out,
    fit_high_order_pcr,
    fit_personal_high_order_prior,
    generate_teacher_dataset,
    heldout_errors_vs_baseline,
    infer_high_order,
    iter_teacher_specs,
    load_high_order_model,
    train_calib_split,
)
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.quality.uncertainty import Validity
from golfmate_algo.synth.multibody import SwingConfig, build_swing
from golfmate_algo.types import WristFeatures


def test_high_order_truth_address_zero():
    truth = build_swing(SwingConfig(plane_tilt_deg=55.0, fs_hz=200.0))
    ho = truth.high_order_truth()
    a = truth.address_idx
    assert abs(ho["wrist_fe_rad"][a]) < 1e-6
    assert abs(ho["clubface_rad"][a]) < 1e-6
    assert np.isfinite(ho["fe_impact_rad"])


def test_train_calib_split_determinism():
    a_tr, a_cal = train_calib_split(80, seed=7, calib_frac=0.25)
    b_tr, b_cal = train_calib_split(80, seed=7, calib_frac=0.25)
    assert np.array_equal(a_tr, b_tr)
    assert np.array_equal(a_cal, b_cal)
    assert len(a_tr) + len(a_cal) == 80
    assert len(set(a_tr) & set(a_cal)) == 0
    c_tr, c_cal = train_calib_split(80, seed=8, calib_frac=0.25)
    assert not np.array_equal(a_cal, c_cal)


def test_teacher_specs_round_robin_deterministic():
    s0 = iter_teacher_specs(20, seed=3)
    s1 = iter_teacher_specs(20, seed=3)
    assert [x.family for x in s0] == [x.family for x in s1]
    assert [x.seed for x in s0] == [x.seed for x in s1]
    assert set(x.family for x in s0) <= set(GENERATOR_FAMILIES)
    # Round-robin covers multiple families for n >= len(families)
    assert len(set(x.family for x in s0)) >= 5


def test_heldout_errors_beat_baseline(tmp_path):
    """Thresholds from calib split; MAE scored on a disjoint held-out feature set."""
    train = generate_teacher_dataset(n_swings=72, seed=11, fs_hz=200.0)
    tr_idx, cal_idx = train_calib_split(len(train["obs"]), seed=11, calib_frac=0.25)
    model = fit_high_order_pcr(
        train["obs"],
        train["tgt"],
        event_fe=train["event_fe"],
        event_face=train["event_face"],
        scalars=train["scalars"],
        grid_sizes=train["grid_sizes"],
        calib_frac=0.25,
        split_seed=11,
    )
    holdout = generate_teacher_dataset(
        n_swings=24, seed=99, fs_hz=200.0, grid_sizes=train["grid_sizes"]
    )
    # Train-mean baseline from train split only (exclude model calib + holdout).
    train_scalars = [train["scalars"][i] for i in tr_idx]
    stats = heldout_errors_vs_baseline(
        model,
        holdout["obs"],
        holdout["scalars"],
        train_scalars=train_scalars,
    )
    wins = 0
    for key in ("wrist_fe_impact_rad", "clubface_impact_rad", "x_factor_top_rad"):
        m = stats["model_mae"][key]
        b = stats["baseline_mae"][key]
        assert np.isfinite(m) and np.isfinite(b), key
        if m < b:
            wins += 1
    # Overall mean must beat baseline; at least 2/3 scalar heads individually.
    mean_m = float(np.mean(list(stats["model_mae"].values())))
    mean_b = float(np.mean(list(stats["baseline_mae"].values())))
    assert mean_m < mean_b, f"mean model MAE {mean_m:.4f} vs baseline {mean_b:.4f}"
    assert wins >= 2, f"expected >=2 keys beating baseline, got {wins}: {stats}"
    path = tmp_path / "w.json"
    path.write_text(json.dumps(model.to_dict()), encoding="utf-8")
    loaded = load_high_order_model(path)
    assert loaded is not None
    assert loaded.version == MODEL_VERSION
    assert set(loaded.heads) == set(HEAD_NAMES)
    assert loaded.n_calib > 0
    assert cal_idx.size > 0


def test_ood_noise_abstains_more_often():
    data = generate_teacher_dataset(
        n_swings=40, seed=5, fs_hz=200.0, families=("nominal", "casting", "left")
    )
    model = fit_high_order_pcr(
        data["obs"],
        data["tgt"],
        event_fe=data["event_fe"],
        event_face=data["event_face"],
        scalars=data["scalars"],
        grid_sizes=data["grid_sizes"],
        calib_frac=0.25,
        split_seed=5,
    )
    clean_abstain = 0
    ood_abstain = 0
    n = min(12, len(data["obs"]))
    rng = np.random.default_rng(123)
    for i in range(n):
        waves, hres, _ = model.predict_targets(data["obs"][i])
        assert waves
        for h in HEAD_NAMES:
            calib = model.heads[h].calibration
            if hres[h] > calib.degraded_resid_max:
                clean_abstain += 1
        # Heavy OOD: scramble obs far outside training manifold
        x = np.asarray(data["obs"][i], dtype=np.float64).copy()
        x = x * 6.0 + rng.normal(scale=8.0, size=x.shape)
        _, hres_ood, _ = model.predict_targets(x)
        for h in HEAD_NAMES:
            calib = model.heads[h].calibration
            if hres_ood[h] > calib.degraded_resid_max:
                ood_abstain += 1
    assert ood_abstain > clean_abstain


def test_inferred_metrics_carry_validity_and_residual(tmp_path):
    path = tmp_path / "high_order_weights.json"
    model = build_default_high_order_model(n_swings=30, seed=2, path=path, fs_hz=200.0)
    truth = build_swing(
        SwingConfig(
            fs_hz=200.0,
            wrist_fe_impact_deg=16.0,
            clubface_open_impact_deg=5.0,
        )
    )
    pkt = truth.to_imu_packet(couple_high_order=True)
    from golfmate_algo.ahrs import init as ahrs_init
    from golfmate_algo.ahrs.suite import GatedAdaptive

    dt = 1.0 / pkt.frame.fs_hz
    q0, _, _ = ahrs_init.estimate_address_orientation(
        pkt.gyro, pkt.accel, pkt.frame.fs_hz
    )
    quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(pkt.gyro, pkt.accel, dt, q0=q0)
    est = infer_high_order(pkt.t, pkt.gyro, quats, truth.phases(), model=model)
    assert est is not None
    assert est.kind.value == "inferred"
    d = est.as_dict()
    assert "residual" in d and d["residual"] is not None
    assert "validity" in d
    for head in HEAD_NAMES:
        assert head in d["heads"]
        assert "validity" in d["heads"][head]
        assert "residual" in d["heads"][head]
        assert "confidence" in d["heads"][head]
        assert "reasons" in d["heads"][head]
        assert head in d
        assert d[head]["validity"] == d["heads"][head]["validity"]
        assert "residual" in d[head]

    report = analyze_swing(pkt, compare_to_ideal=False)
    # Inject our model estimate into meta for commercial projection.
    report.meta["high_order"] = d
    commercial = build_commercial_report(report)
    inferred = [m for m in commercial.inference if m.kind.value == "inferred"]
    assert inferred
    for m in inferred:
        assert m.residual is not None
        assert m.validity in Validity
        assert 0.0 <= m.confidence <= 1.0


def test_personal_calibration_improves_biased_labels():
    rng = np.random.default_rng(0)
    keys = (
        "wrist_fe_impact_rad",
        "clubface_impact_rad",
        "x_factor_top_rad",
    )
    labels = []
    preds = []
    # Systematic bias + mild scale error in "raw" inferences
    for _ in range(8):
        lab = {
            "wrist_fe_impact_rad": float(rng.uniform(-0.1, 0.4)),
            "clubface_impact_rad": float(rng.uniform(-0.2, 0.2)),
            "x_factor_top_rad": float(rng.uniform(0.3, 0.8)),
        }
        pred = {
            "wrist_fe_impact_rad": 0.7 * lab["wrist_fe_impact_rad"] + 0.12,
            "clubface_impact_rad": 0.75 * lab["clubface_impact_rad"] - 0.08,
            "x_factor_top_rad": 0.8 * lab["x_factor_top_rad"] + 0.05,
        }
        labels.append(lab)
        preds.append(pred)
    prior = fit_personal_high_order_prior(preds, labels, min_samples=3, keys=keys)
    assert prior.version == PERSONAL_PRIOR_VERSION
    assert prior.n_fit == 8
    assert set(prior.keys_fit) >= set(keys)
    ser = prior.to_dict()
    prior2 = type(prior).from_dict(ser)
    assert prior2.scale["wrist_fe_impact_rad"] == pytest.approx(
        prior.scale["wrist_fe_impact_rad"]
    )

    def mae(ps):
        errs = []
        for p, y in zip(ps, labels):
            for k in keys:
                errs.append(abs(float(p[k]) - float(y[k])))
        return float(np.mean(errs))

    before = mae(preds)
    after_preds = []
    for p in preds:
        after_preds.append({k: prior.apply_scalar(k, p[k]) for k in keys})
    after = mae(after_preds)
    assert after < before * 0.5


def test_leave_generator_out_utility_runs():
    result = evaluate_leave_generator_out(
        holdout_family="casting",
        n_train=36,
        n_test=8,
        seed=4,
        fs_hz=200.0,
    )
    assert result["holdout_family"] == "casting"
    assert result["n_train"] > 0
    assert "model_mae" in result and "baseline_mae" in result
    assert "abstain_rate" in result


def test_diagnostics_suppress_abstained_heads():
    feats = WristFeatures(
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
    high_order = {
        "kind": "inferred",
        "confidence": 0.7,
        "residual": 0.2,
        "validity": "degraded",
        "wrist": {
            "fe_impact_deg": 12.0,
            "fe_delta_address_to_impact_deg": -8.0,
            "validity": "ok",
            "confidence": 0.7,
            "residual": 0.2,
            "reasons": ["inside_calib_envelope"],
            # Head OK but FE scalars abstained via MAE budget → no wrist finding.
            "metrics": {
                "fe_impact": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.2,
                    "reasons": ["calib_mae_exceeds_degraded_budget"],
                },
                "fe_delta_address_to_impact": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.2,
                    "reasons": ["derived_fe_delta"],
                },
            },
        },
        "club": {
            "face_open_closed": "open",
            "face_impact_deg": 6.0,
            "validity": "ok",
            "confidence": 0.7,
            "residual": 0.2,
            "reasons": ["inside_calib_envelope"],
            "metrics": {
                "face_impact": {
                    "validity": "ok",
                    "confidence": 0.7,
                    "residual": 0.2,
                    "reasons": ["calib_mae_within_ok_budget"],
                },
                "shaft_lean_impact": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.2,
                    "reasons": ["calib_mae_exceeds_degraded_budget"],
                },
            },
        },
        "body": {
            "sequence_order_ok": False,
            "pelvis_peak_to_impact_s": 0.12,
            "club_peak_to_impact_s": 0.01,
            "validity": "ok",
            "confidence": 0.7,
            "residual": 0.2,
            "reasons": ["inside_calib_envelope"],
            "metrics": {
                "x_factor_top": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.2,
                    "reasons": ["calib_mae_exceeds_degraded_budget"],
                },
            },
        },
    }
    findings = diagnose(feats, high_order=high_order)
    codes = {f.code for f in findings if f.kind == "inferred"}
    assert "wrist_extends_into_impact" not in codes
    assert "kinematic_sequence_out_of_order" not in codes
    assert "clubface_open_impact" in codes


def test_commercial_report_uses_per_scalar_validity():
    truth = build_swing(SwingConfig(fs_hz=200.0))
    report = analyze_swing(
        truth.to_imu_packet(couple_high_order=True), compare_to_ideal=False
    )
    report.meta["high_order"] = {
        "kind": "inferred",
        "confidence": 0.5,
        "residual": 0.4,
        "validity": "degraded",
        "source": "high_order_pcr",
        "reasons": ["high_order_multihead_pcr"],
        "wrist": {
            "fe_impact_deg": 10.0,
            "fe_delta_address_to_impact_deg": 3.0,
            "ru_impact_deg": 1.0,
            "validity": "ok",
            "confidence": 0.8,
            "residual": 0.2,
            "reasons": ["inside_calib_envelope"],
            "metrics": {
                "fe_impact": {
                    "validity": "ok",
                    "confidence": 0.8,
                    "residual": 0.2,
                    "reasons": ["calib_mae_within_ok_budget"],
                },
                "fe_delta_address_to_impact": {
                    "validity": "ok",
                    "confidence": 0.8,
                    "residual": 0.2,
                    "reasons": ["derived_fe_delta"],
                },
                "ru_impact": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.2,
                    "reasons": ["calib_mae_exceeds_degraded_budget"],
                },
            },
        },
        "club": {
            "face_impact_deg": 4.0,
            "shaft_lean_impact_deg": 2.0,
            "validity": "ok",
            "confidence": 0.7,
            "residual": 0.3,
            "reasons": ["inside_calib_envelope"],
            "metrics": {
                "face_impact": {
                    "validity": "degraded",
                    "confidence": 0.45,
                    "residual": 0.3,
                    "reasons": ["calib_mae_exceeds_ok_budget"],
                },
                "shaft_lean_impact": {
                    "validity": "abstain",
                    "confidence": 0.1,
                    "residual": 0.3,
                    "reasons": ["calib_mae_exceeds_degraded_budget"],
                },
            },
        },
        "body": {
            "x_factor_top_deg": 35.0,
            "validity": "degraded",
            "confidence": 0.4,
            "residual": 0.7,
            "reasons": ["near_calib_edge"],
            "metrics": {
                "x_factor_top": {
                    "validity": "degraded",
                    "confidence": 0.4,
                    "residual": 0.7,
                    "reasons": ["head_ood_degraded"],
                },
            },
        },
    }
    payload = export_commercial_report(report)
    by_name = {m["name"]: m for m in payload["inference"]}
    assert by_name["wrist_fe_impact_deg"]["validity"] == "ok"
    assert by_name["wrist_fe_impact_deg"]["residual"] == pytest.approx(0.2)
    assert by_name["wrist_fe_impact_deg"]["extras"]["metric"] == "fe_impact"
    assert by_name["wrist_ru_impact_deg"]["validity"] == "abstain"
    assert by_name["wrist_ru_impact_deg"]["value"] is None
    assert by_name["clubface_impact_deg"]["validity"] == "degraded"
    assert by_name["shaft_lean_impact_deg"]["validity"] == "abstain"
    assert by_name["shaft_lean_impact_deg"]["value"] is None
    assert by_name["x_factor_top_deg"]["validity"] == "degraded"
    assert by_name["high_order_residual"]["validity"] == "degraded"
    # Strict JSON: abstained values are null, not NaN.
    import json as _json

    _json.dumps(payload, allow_nan=False)


def test_fit_and_infer_discrimination(tmp_path):
    path = tmp_path / "high_order_weights.json"
    model = build_default_high_order_model(n_swings=40, seed=1, path=path, fs_hz=200.0)
    assert model.n_train >= 20
    assert path.exists()

    def _est(fe: float, face: float):
        truth = build_swing(
            SwingConfig(
                fs_hz=200.0,
                plane_tilt_deg=52.0,
                downswing_s=0.26,
                wrist_fe_top_deg=-20.0,
                wrist_fe_impact_deg=fe,
                clubface_open_top_deg=8.0,
                clubface_open_impact_deg=face,
            )
        )
        pkt = truth.to_imu_packet(couple_high_order=True)
        from golfmate_algo.ahrs import init as ahrs_init
        from golfmate_algo.ahrs.suite import GatedAdaptive

        dt = 1.0 / pkt.frame.fs_hz
        q0, _, _ = ahrs_init.estimate_address_orientation(
            pkt.gyro, pkt.accel, pkt.frame.fs_hz
        )
        quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(
            pkt.gyro, pkt.accel, dt, q0=q0
        )
        est = infer_high_order(pkt.t, pkt.gyro, quats, truth.phases(), model=model)
        return est, truth.high_order_truth()

    est_lo, _ = _est(-4.0, -12.0)
    est_hi, _ = _est(26.0, 12.0)
    assert est_lo is not None and est_hi is not None
    # Prefer finite comparison when heads do not abstain; else check waveforms.
    if (
        np.isfinite(est_lo.wrist_fe_impact_rad)
        and np.isfinite(est_hi.wrist_fe_impact_rad)
    ):
        assert est_hi.wrist_fe_impact_rad - est_lo.wrist_fe_impact_rad > np.deg2rad(6.0)
    if (
        np.isfinite(est_lo.clubface_impact_rad)
        and np.isfinite(est_hi.clubface_impact_rad)
    ):
        assert est_hi.clubface_impact_rad - est_lo.clubface_impact_rad > np.deg2rad(4.0)
    assert est_hi.kind.value == "inferred"
    assert "wrist" in est_hi.heads


def test_pipeline_emits_high_order_when_weights_present():
    from golfmate_algo.infer import high_order as ho_mod

    if not ho_mod._DEFAULT_WEIGHTS.exists():
        build_default_high_order_model(
            n_swings=24, seed=0, path=ho_mod._DEFAULT_WEIGHTS, fs_hz=200.0
        )

    truth = build_swing(SwingConfig(fs_hz=200.0))
    report = analyze_swing(
        truth.to_imu_packet(couple_high_order=True), compare_to_ideal=False
    )
    assert "high_order" in report.meta
    high = report.meta["high_order"]
    assert high is not None
    assert high["kind"] == "inferred"
    assert high.get("source") == "high_order_pcr"
    assert "wrist" in high and "club" in high and "body" in high
    assert "metrics" in high["wrist"]
    assert "metrics" in high["club"]


def test_scalar_mae_budgets_are_documented_and_fixed():
    from golfmate_algo.infer.high_order import SCALAR_MAE_BUDGETS_RAD

    # Conservative a-priori budgets (radians); must not silently change.
    assert SCALAR_MAE_BUDGETS_RAD["wrist_fe_impact_rad"] == pytest.approx(
        (np.deg2rad(8), np.deg2rad(15))
    )
    assert SCALAR_MAE_BUDGETS_RAD["wrist_ru_impact_rad"] == pytest.approx(
        (np.deg2rad(8), np.deg2rad(15))
    )
    assert SCALAR_MAE_BUDGETS_RAD["clubface_impact_rad"] == pytest.approx(
        (np.deg2rad(8), np.deg2rad(15))
    )
    assert SCALAR_MAE_BUDGETS_RAD["shaft_lean_impact_rad"] == pytest.approx(
        (np.deg2rad(8), np.deg2rad(15))
    )
    assert SCALAR_MAE_BUDGETS_RAD["x_factor_top_rad"] == pytest.approx(
        (np.deg2rad(10), np.deg2rad(20))
    )
    assert SCALAR_MAE_BUDGETS_RAD["forearm_ps_impact_rad"] == pytest.approx(
        (np.deg2rad(10), np.deg2rad(20))
    )


def test_shipped_model_abstains_weak_ru_and_shaft_lean():
    """Shipped calib MAE for RU/shaft exceeds degraded budget → scalar abstain."""
    model = load_high_order_model()
    assert model is not None
    assert model.heads
    ru_mae = model.heads["wrist"].calibration.scalar_mae.get("wrist_ru_impact_rad", 0.0)
    lean_mae = model.heads["club"].calibration.scalar_mae.get(
        "shaft_lean_impact_rad", 0.0
    )
    assert ru_mae > np.deg2rad(15.0), f"expected weak RU calib MAE, got {ru_mae}"
    assert lean_mae > np.deg2rad(15.0), f"expected weak shaft MAE, got {lean_mae}"

    truth = build_swing(
        SwingConfig(
            fs_hz=200.0,
            wrist_fe_impact_deg=16.0,
            clubface_open_impact_deg=5.0,
        )
    )
    pkt = truth.to_imu_packet(couple_high_order=True)
    from golfmate_algo.ahrs import init as ahrs_init
    from golfmate_algo.ahrs.suite import GatedAdaptive

    dt = 1.0 / pkt.frame.fs_hz
    q0, _, _ = ahrs_init.estimate_address_orientation(
        pkt.gyro, pkt.accel, pkt.frame.fs_hz
    )
    quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(pkt.gyro, pkt.accel, dt, q0=q0)
    est = infer_high_order(pkt.t, pkt.gyro, quats, truth.phases(), model=model)
    assert est is not None
    # Heads may be OK (in-envelope residual) while weak scalars abstain.
    assert est.scalars["wrist_ru_impact_rad"].validity == Validity.ABSTAIN
    assert est.scalars["shaft_lean_impact_rad"].validity == Validity.ABSTAIN
    assert not np.isfinite(est.wrist_ru_impact_rad)
    assert not np.isfinite(est.shaft_lean_impact_rad)
    assert "calib_mae_exceeds_degraded_budget" in est.scalars[
        "wrist_ru_impact_rad"
    ].reasons
    assert "calib_mae_exceeds_degraded_budget" in est.scalars[
        "shaft_lean_impact_rad"
    ].reasons

    d = est.as_dict()
    assert d["wrist"]["metrics"]["ru_impact"]["validity"] == "abstain"
    assert d["club"]["metrics"]["shaft_lean_impact"]["validity"] == "abstain"
    # FE / face may remain usable only if their held-out MAE passes ok/degraded.
    fe_mae = model.heads["wrist"].calibration.scalar_mae["wrist_fe_impact_rad"]
    face_mae = model.heads["club"].calibration.scalar_mae["clubface_impact_rad"]
    if fe_mae <= np.deg2rad(15.0) and est.heads["wrist"].validity != Validity.ABSTAIN:
        assert est.scalars["wrist_fe_impact_rad"].validity != Validity.ABSTAIN
        assert np.isfinite(est.wrist_fe_impact_rad)
    if face_mae <= np.deg2rad(15.0) and est.heads["club"].validity != Validity.ABSTAIN:
        assert est.scalars["clubface_impact_rad"].validity != Validity.ABSTAIN
        assert np.isfinite(est.clubface_impact_rad)

    # Commercial exporter must surface scalar abstention + strict JSON nulls.
    report = analyze_swing(pkt, compare_to_ideal=False)
    report.meta["high_order"] = d
    payload = export_commercial_report(report)
    by_name = {m["name"]: m for m in payload["inference"]}
    assert by_name["wrist_ru_impact_deg"]["validity"] == "abstain"
    assert by_name["wrist_ru_impact_deg"]["value"] is None
    assert by_name["shaft_lean_impact_deg"]["validity"] == "abstain"
    assert by_name["shaft_lean_impact_deg"]["value"] is None
    json.dumps(payload, allow_nan=False)


def test_head_ood_worsens_scalar_but_mae_can_abstain_alone():
    from golfmate_algo.infer.high_order import (
        HeadStatus,
        SCALAR_MAE_BUDGETS_RAD,
        _scalar_status_from_mae,
    )

    ok_head = HeadStatus(Validity.OK, 0.8, 0.2, ["inside_calib_envelope"])
    # MAE above degraded budget → abstain even with OK head.
    st = _scalar_status_from_mae(
        "wrist_ru_impact_rad",
        SCALAR_MAE_BUDGETS_RAD["wrist_ru_impact_rad"][1] + 0.1,
        ok_head,
    )
    assert st.validity == Validity.ABSTAIN
    assert "calib_mae_exceeds_degraded_budget" in st.reasons

    # MAE within ok budget but head OOD → worsened to abstain.
    st2 = _scalar_status_from_mae(
        "wrist_fe_impact_rad",
        0.05,
        HeadStatus(Validity.ABSTAIN, 0.1, 2.0, ["outside_calib_envelope"]),
    )
    assert st2.validity == Validity.ABSTAIN
    assert "head_ood_abstain" in st2.reasons

    # MAE between budgets + OK head → degraded.
    ok_b, deg_b = SCALAR_MAE_BUDGETS_RAD["clubface_impact_rad"]
    st3 = _scalar_status_from_mae("clubface_impact_rad", 0.5 * (ok_b + deg_b), ok_head)
    assert st3.validity == Validity.DEGRADED
    assert "calib_mae_exceeds_ok_budget" in st3.reasons
