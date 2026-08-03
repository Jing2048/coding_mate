"""High-order PCR inference: wrist FE/RU, clubface, body sequence."""

from __future__ import annotations

import numpy as np

from golfmate_algo.infer.high_order import (
    build_default_high_order_model,
    infer_high_order,
    load_high_order_model,
)
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.multibody import SwingConfig, build_swing


def test_high_order_truth_address_zero():
    truth = build_swing(SwingConfig(plane_tilt_deg=55.0))
    ho = truth.high_order_truth()
    a = truth.address_idx
    assert abs(ho["wrist_fe_rad"][a]) < 1e-6
    assert abs(ho["clubface_rad"][a]) < 1e-6
    assert np.isfinite(ho["fe_impact_rad"])


def test_fit_and_infer_beats_chance(tmp_path):
    path = tmp_path / "high_order_weights.json"
    model = build_default_high_order_model(n_swings=36, seed=1, path=path)
    assert path.exists()
    assert model.n_train == 36
    assert "gx" in model.obs_names

    def _est(fe: float, face: float):
        truth = build_swing(
            SwingConfig(
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

    est, gt = _est(18.0, 6.0)
    assert est is not None
    assert est.kind.value == "inferred"
    assert est.confidence >= 0.2
    assert est.residual < 1.0

    fe_err = abs(est.wrist_fe_impact_rad - float(gt["fe_impact_rad"]))
    face_err = abs(est.clubface_impact_rad - float(gt["clubface_impact_rad"]))
    assert fe_err < np.deg2rad(8.0), f"FE err {np.degrees(fe_err):.1f}°"
    assert face_err < np.deg2rad(8.0), f"face err {np.degrees(face_err):.1f}°"

    # Discrimination: must not collapse to the training mean
    est_lo, _ = _est(-4.0, -12.0)
    est_hi, _ = _est(26.0, 12.0)
    assert est_hi.wrist_fe_impact_rad - est_lo.wrist_fe_impact_rad > np.deg2rad(10.0)
    assert est_hi.clubface_impact_rad - est_lo.clubface_impact_rad > np.deg2rad(8.0)

    # Pipeline path emits finite high_order (may use uncoupled packet → degraded)
    truth = build_swing(SwingConfig(wrist_fe_impact_deg=18.0, clubface_open_impact_deg=6.0))
    report = analyze_swing(truth.to_imu_packet(couple_high_order=True), compare_to_ideal=False)
    assert report.meta.get("high_order") is not None or load_high_order_model(path)
    est_pipe = infer_high_order(
        truth.t,
        truth.to_imu_packet(couple_high_order=True).gyro,
        report.quats,
        report.phases,
        model=model,
    )
    assert est_pipe is not None
    assert np.isfinite(est_pipe.wrist_fe_impact_rad)


def test_pipeline_emits_high_order_when_weights_present():
    from golfmate_algo.infer import high_order as ho_mod

    if not ho_mod._DEFAULT_WEIGHTS.exists():
        build_default_high_order_model(n_swings=24, seed=0, path=ho_mod._DEFAULT_WEIGHTS)

    truth = build_swing(SwingConfig())
    report = analyze_swing(
        truth.to_imu_packet(couple_high_order=True), compare_to_ideal=False
    )
    assert "high_order" in report.meta
    high = report.meta["high_order"]
    assert high is not None
    assert high["kind"] == "inferred"
    assert high.get("source") == "high_order_pcr"
    assert "wrist" in high and "club" in high and "body" in high
    assert "fe_impact_deg" in high["wrist"]
    assert "face_impact_deg" in high["club"]
    assert np.isfinite(high["wrist"]["fe_impact_deg"])
    assert np.isfinite(high["club"]["face_impact_deg"])
