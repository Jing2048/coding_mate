"""Tests for extreme-opt modules: dual-path, CROP-lite, hybrid, proxies."""

from __future__ import annotations

import numpy as np

from golfmate_algo.biomechanics.proxies import estimate_biomech_proxies, fit_proxy_weights
from golfmate_algo.calib.crop_lite import crop_lite_correct
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.signal.dynamic_range import signed_log_compress, split_dual_path
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.synth.multibody import build_swing
from golfmate_algo.synth.violations import apply_violations
from golfmate_algo.traj.hybrid import estimate_hybrid_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm


def test_signed_log_preserves_small_signal_slope():
    x = np.linspace(-1.0, 1.0, 21)
    y = signed_log_compress(x, scale=9.80665)
    # Near zero, slope ≈ 1
    assert abs(y[10] - x[10]) < 1e-9
    assert abs((y[11] - y[9]) / (x[11] - x[9]) - 1.0) < 0.05
    # Large spikes are attenuated
    spike = np.array([50.0, -50.0])
    soft = signed_log_compress(spike, scale=9.80665)
    assert np.all(np.abs(soft) < np.abs(spike))


def test_dual_path_keeps_raw_accel_for_events():
    syn = planar_circular_swing()
    dual = split_dual_path(syn.packet.gyro, syn.packet.accel, syn.packet.frame.fs_hz)
    assert np.allclose(dual.accel_raw, syn.packet.accel)
    assert dual.accel_ahrs.shape == syn.packet.accel.shape
    assert not np.allclose(dual.accel_ahrs, dual.accel_raw)


def test_crop_lite_reduces_rest_gyro():
    syn = planar_circular_swing()
    ph = syn.phases_true
    # Inject a small constant gyro bias
    gyro_b = syn.packet.gyro + np.array([0.02, -0.01, 0.015])
    out = crop_lite_correct(
        gyro_b,
        syn.packet.accel,
        syn.packet.frame.fs_hz,
        address_idx=ph.address_idx,
        finish_idx=ph.finish_idx,
    )
    assert out.success
    assert np.linalg.norm(out.delta_gyro) > 0.005
    # Corrected rest gyro should be smaller than biased
    rest = slice(0, ph.address_idx + 1)
    assert np.linalg.norm(out.gyro_corr[rest].mean(axis=0)) < np.linalg.norm(
        gyro_b[rest].mean(axis=0)
    )


def test_hybrid_on_analytic_not_worse_than_rigid():
    syn = planar_circular_swing(radius_m=0.55, plane_tilt_deg=55.0)
    dt = 1.0 / syn.packet.frame.fs_hz
    ph = syn.phases_true
    la = estimate_lever_arm(syn.quats_true, syn.packet.gyro, syn.packet.accel, dt)
    hy = estimate_hybrid_trajectory(
        syn.quats_true, syn.packet.gyro, syn.packet.accel, dt, ph
    )
    truth = syn.positions_true - syn.positions_true[ph.address_idx]
    window = slice(ph.address_idx, ph.finish_idx + 1)
    e_la = float(
        np.mean(np.linalg.norm(la.positions[window] - la.positions[ph.address_idx] - truth[window], axis=1))
    )
    e_hy = float(
        np.mean(
            np.linalg.norm(
                hy.positions[window] - hy.positions[ph.address_idx] - truth[window], axis=1
            )
        )
    )
    # Hybrid should match rigid upper bound on isomorphic analytic (gated off)
    assert e_hy < e_la * 1.05 + 0.005
    assert abs(e_hy - e_la) < 0.01


def test_hybrid_residual_rises_on_violation():
    from golfmate_algo.synth.violations import mild_violation

    truth = build_swing()
    dt = 1.0 / truth.config.fs_hz
    clean = estimate_lever_arm(truth.sensor_quat, truth.gyro_body, truth.accel_body, dt)
    gyro_v, accel_v, _ = apply_violations(
        truth.t,
        truth.gyro_body,
        truth.accel_body,
        quats_true=truth.sensor_quat,
        positions_true=truth.sensor_pos,
        impact_idx=truth.impact_idx,
        spec=mild_violation(seed=0),
    )
    v_la = estimate_lever_arm(truth.sensor_quat, gyro_v, accel_v, dt)
    assert v_la.residual_rms_m_s2 > clean.residual_rms_m_s2 * 1.15


def test_pipeline_default_hybrid_meta():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet)
    assert report.meta.get("trajectory") == "hybrid"
    assert "crop_success" in report.meta
    assert "blend_w_lever" in report.meta
    assert "x_factor_proxy_deg" in report.features.extras
    assert report.meta["biomech_proxies"]["is_proxy"] is True


def test_proxies_fit_and_estimate():
    payload = fit_proxy_weights(n_swings=8, seed=1)
    assert "targets" in payload
    assert "x_factor_proxy_deg" in payload["targets"]
    truth = build_swing()
    ph = truth.phases()
    proxies = estimate_biomech_proxies(truth.t, truth.gyro_body, ph)
    assert proxies.is_proxy
    assert 0.05 <= proxies.confidence <= 0.95
