"""Adversarial and regression tests.

These lock in the benchmark conclusions and probe failure modes that a clean
synthetic swing would never reveal: sensor clipping, dropped packets, timing
jitter, degenerate inputs and unphysical parameters.
"""

from __future__ import annotations

import numpy as np
import pytest

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs import suite
from golfmate_algo.bench.harness import _yaw_align, orientation_error_deg
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.math import so3
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.session import make_session
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.types import ImuPacket, SensorFrame


def _corrupt(swing, params):
    return apply_imu_errors(
        swing.packet.t, swing.packet.gyro, swing.packet.accel, params
    )


# ---------------------------------------------------------------- generators


def test_synth_accel_is_consistent_with_position():
    """Numerically differentiating the truth path must reproduce the accel."""
    syn = planar_circular_swing(fs_hz=1000.0, impact_shock_g=0.0)
    dt = 1.0 / 1000.0
    acc_num = np.gradient(np.gradient(syn.positions_true, dt, axis=0), dt, axis=0)
    inner = slice(20, -20)
    rebuilt = np.zeros_like(acc_num)
    for i in range(syn.packet.t.shape[0]):
        R = so3.quat_to_rotmat(syn.quats_true[i])
        rebuilt[i] = R @ syn.packet.accel[i] + so3.G_WORLD
    err = np.linalg.norm(rebuilt[inner] - acc_num[inner], axis=1)
    assert float(np.max(err)) < 0.5


def test_synth_gyro_integrates_to_truth():
    syn = planar_circular_swing(fs_hz=500.0)
    dt = 1.0 / 500.0
    q = syn.quats_true[0].copy()
    worst = 0.0
    for i in range(syn.packet.t.shape[0] - 1):
        q = so3.integrate_gyro_rk4(q, syn.packet.gyro[i], dt)
        worst = max(worst, np.degrees(so3.geodesic_distance(q, syn.quats_true[i + 1])))
    assert worst < 1.0


def test_casting_generator_moves_peak_earlier():
    normal = planar_circular_swing(casting=False)
    cast = planar_circular_swing(casting=True)
    assert cast.meta["peak_to_impact_s"] > normal.meta["peak_to_impact_s"] + 0.05


def test_session_is_self_consistent():
    s = make_session(n_swings=2, rest_between_s=1.0)
    dt = 1.0 / s.packet.frame.fs_hz
    q = s.quats_true[0].copy()
    worst = 0.0
    for i in range(s.packet.t.shape[0] - 1):
        q = so3.integrate_gyro_rk4(q, s.packet.gyro[i], dt)
        worst = max(worst, np.degrees(so3.geodesic_distance(q, s.quats_true[i + 1])))
    assert worst < 5.0
    rest = s.rest_mask_true
    pred = np.array(
        [-so3.quat_to_rotmat(s.quats_true[i]).T @ so3.G_WORLD for i in np.where(rest)[0]]
    )
    assert float(np.max(np.abs(pred - s.packet.accel[rest]))) < 1e-9


# ------------------------------------------------------------------ gating


def test_gate_closes_at_top_where_alpha_peaks():
    """The reversal has near-zero rate but peak angular acceleration."""
    gate = suite.DynamicsGate()
    quiet = gate(0.1, 9.81, 0.5)
    reversal = gate(0.1, 9.81, 60.0)
    strike = gate(14.0, 98.0, 3.0)
    assert quiet > 0.5
    assert reversal < 0.05
    assert strike < 1e-6


def test_gated_filter_never_much_worse_than_integration_in_swing():
    syn = planar_circular_swing()
    dt = 1.0 / syn.packet.frame.fs_hz
    q0, _, _ = ahrs_init.estimate_address_orientation(
        syn.packet.gyro, syn.packet.accel, syn.packet.frame.fs_hz
    )
    e = {}
    for est in (suite.GyroOnly(), suite.GatedAdaptive()):
        q, _ = est.run(syn.packet.gyro, syn.packet.accel, dt, q0=q0)
        err = orientation_error_deg(_yaw_align(q, syn.quats_true), syn.quats_true)
        ph = syn.phases_true
        e[est.name] = float(np.mean(err[ph.top_idx : ph.impact_idx + 1]))
    assert e["gated_adaptive"] < e["gyro_only"] + 1.0


def test_gated_filter_beats_integration_over_a_session():
    """Bounded-drift filtering must win once bias has time to accumulate."""
    s = make_session(n_swings=4, rest_between_s=2.0, seed=0)
    fs = s.packet.frame.fs_hz
    _, gyro, accel, _ = apply_imu_errors(
        s.packet.t, s.packet.gyro, s.packet.accel, ImuErrorParams.consumer_grade(seed=0)
    )
    q0, _, _ = ahrs_init.estimate_address_orientation(gyro, accel, fs)
    res = {}
    for est in (suite.GyroOnly(), suite.GatedAdaptive()):
        q, _ = est.run(gyro, accel, 1.0 / fs, q0=q0)
        res[est.name] = float(
            np.mean(orientation_error_deg(_yaw_align(q, s.quats_true), s.quats_true))
        )
    assert res["gated_adaptive"] < 0.5 * res["gyro_only"]


# -------------------------------------------------------------- trajectory


def test_lever_arm_recovers_radius_and_reports_null_space():
    syn = planar_circular_swing(radius_m=0.5)
    dt = 1.0 / syn.packet.frame.fs_hz
    la = estimate_lever_arm(syn.quats_true, syn.packet.gyro, syn.packet.accel, dt)
    assert abs(la.radius_m - 0.5) < 0.05
    # A planar swing rotates about one axis, so exactly one direction of the
    # lever arm is unobservable and must be reported rather than silently fitted.
    assert la.rank == 2
    assert la.unobservable_directions.shape[0] == 1
    assert la.valid


def test_lever_arm_beats_dead_reckoning_under_sensor_noise():
    from golfmate_algo.traj.dead_reckon import reconstruct_trajectory

    syn = planar_circular_swing()
    dt = 1.0 / syn.packet.frame.fs_hz
    _, gyro, accel, _ = _corrupt(syn, ImuErrorParams.consumer_grade(seed=1))
    ph = syn.phases_true
    truth = syn.positions_true - syn.positions_true[ph.address_idx]
    win = slice(ph.address_idx, ph.finish_idx + 1)

    la = estimate_lever_arm(syn.quats_true, gyro, accel, dt)
    p_la = la.positions - la.positions[ph.address_idx]
    _, _, p_dr = reconstruct_trajectory(syn.quats_true, accel, dt, phases=ph)
    p_dr = p_dr - p_dr[ph.address_idx]

    e_la = float(np.mean(np.linalg.norm(p_la[win] - truth[win], axis=1)))
    e_dr = float(np.mean(np.linalg.norm(p_dr[win] - truth[win], axis=1)))
    assert e_la < e_dr
    assert e_la < 0.15  # metres


# ------------------------------------------------------------------ events


@pytest.mark.parametrize("level", ["ideal", "consumer"])
def test_event_accuracy_regression(level: str):
    """Locks event timing near published single-IMU segmentation accuracy."""
    budgets_ms = {"ideal": 20.0, "consumer": 40.0}
    params = (
        ImuErrorParams.ideal() if level == "ideal" else ImuErrorParams.consumer_grade(seed=3)
    )
    worst = 0.0
    for kwargs in (
        dict(casting=False, backswing_s=0.75, downswing_s=0.25),
        dict(casting=True, backswing_s=0.85, downswing_s=0.28),
        dict(casting=False, backswing_s=0.62, downswing_s=0.20),
    ):
        syn = planar_circular_swing(**kwargs)
        _, gyro, accel, _ = _corrupt(syn, params)
        det = detect_phases_segmental(syn.packet.t, gyro, accel)
        fs = syn.packet.frame.fs_hz
        for name in ("address", "top", "impact", "finish"):
            err = abs(getattr(det, f"{name}_idx") - getattr(syn.phases_true, f"{name}_idx"))
            worst = max(worst, err / fs * 1000.0)
    assert worst <= budgets_ms[level]


def test_impact_detection_survives_accel_clipping():
    syn = planar_circular_swing()
    p = ImuErrorParams.ideal()
    p.accel_range_g = 8.0  # clips the strike transient hard
    _, gyro, accel, rep = _corrupt(syn, p)
    assert rep.accel_saturated_frac > 0.0
    det = detect_phases_segmental(syn.packet.t, gyro, accel)
    err_ms = abs(det.impact_idx - syn.phases_true.impact_idx) / 200.0 * 1000.0
    assert err_ms < 60.0


def test_pipeline_survives_dropouts_and_jitter():
    syn = planar_circular_swing()
    p = ImuErrorParams.consumer_grade(seed=7)
    p.dropout_prob = 0.01
    p.dropout_max_len = 5
    p.jitter_std_s = 0.0008
    _, gyro, accel, rep = _corrupt(syn, p)
    assert rep.dropout_frac > 0.0
    packet = ImuPacket(
        frame=SensorFrame(fs_hz=200.0), t=syn.packet.t, gyro=gyro, accel=accel
    )
    report = analyze_swing(packet)
    assert np.all(np.isfinite(report.quats))
    assert np.all(np.isfinite(report.positions))
    report.phases.validate_order()


# ------------------------------------------------------- degenerate inputs


def test_no_motion_raises_rather_than_returning_nonsense():
    n = 400
    t = np.arange(n) / 200.0
    gyro = np.zeros((n, 3))
    accel = np.tile([0.0, 0.0, 9.80665], (n, 1))
    with pytest.raises(ValueError):
        detect_phases_segmental(t, gyro, accel)


def test_filters_reject_nan_without_propagating():
    n = 100
    gyro = np.zeros((n, 3))
    accel = np.tile([0.0, 0.0, 9.80665], (n, 1))
    gyro[10] = np.nan
    accel[20] = np.inf
    for est in suite.make_default_suite():
        q, _ = est.run(gyro, accel, 0.005)
        assert np.all(np.isfinite(q)), est.name
        assert np.allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-9), est.name


def test_zero_length_and_tiny_inputs():
    for est in suite.make_default_suite():
        q, _ = est.run(np.zeros((0, 3)), np.zeros((0, 3)), 0.005)
        assert q.shape == (0, 4)
    with pytest.raises(ValueError):
        detect_phases_segmental(np.arange(5) / 200.0, np.zeros((5, 3)), np.zeros((5, 3)))


def test_address_init_quality_flags_a_moving_start():
    syn = planar_circular_swing(address_s=0.02)
    q0, _, m = ahrs_init.estimate_address_orientation(
        syn.packet.gyro, syn.packet.accel, 200.0
    )
    assert np.isfinite(q0).all()
    assert m["quality"] in {"good", "usable", "poor"}
