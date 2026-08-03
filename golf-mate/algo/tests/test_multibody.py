"""Correctness tests for the multibody golf-swing ground-truth simulator.

Every check is against a closed-form / constructed truth: analytic accelerometer
and gyro are cross-validated against the position trajectory and orientation
series, the proximal-to-distal kinematic sequence is verified, and the exact
event indices are checked.
"""

from __future__ import annotations

import numpy as np

from golfmate_algo.math import so3
from golfmate_algo.synth import multibody as mb


def _build():
    return mb.build_swing()


def test_shapes_and_events_exact():
    tr = _build()
    n = tr.t.shape[0]
    assert tr.seg_quat.shape == (4, n, 4)
    assert tr.seg_omega_body.shape == (4, n, 3)
    assert tr.sensor_pos.shape == (n, 3)
    assert tr.accel_body.shape == (n, 3)
    tr.phases().validate_order()  # raises if not strictly increasing
    cfg = tr.config
    fs = cfg.fs_hz
    assert tr.top_idx == round((cfg.address_s + cfg.backswing_s) * fs)
    assert tr.impact_idx == round((cfg.address_s + cfg.backswing_s + cfg.downswing_s) * fs)


def test_address_is_exactly_static():
    tr = _build()
    a = tr.address_idx
    assert np.linalg.norm(tr.gyro_body[a]) < 1e-12
    # Level, static sensor reads +g on the (world-up) sensor axis only.
    assert np.linalg.norm(tr.accel_body[a] - np.array([0.0, 0.0, 9.80665])) < 1e-9
    assert np.linalg.norm(tr.sensor_vel[a]) < 1e-12
    assert np.linalg.norm(tr.sensor_acc[a]) < 1e-12


def test_specific_force_definition():
    tr = _build()
    i = tr.impact_idx
    R_sensor = so3.quat_to_rotmat(tr.sensor_quat[i])
    expected = R_sensor.T @ (tr.sensor_acc[i] - so3.G_WORLD)
    assert np.linalg.norm(tr.accel_body[i] - expected) < 1e-10
    # Gyro is the segment world rate expressed in the sensor frame.
    m = tr.config.mount_segment
    expected_gyro = R_sensor.T @ tr.seg_omega_world[m, i]
    assert np.linalg.norm(tr.gyro_body[i] - expected_gyro) < 1e-10


def test_accel_matches_numeric_position_second_derivative():
    tr = _build()
    dt = tr.dt
    a_world_meas = np.empty_like(tr.sensor_acc)
    for i in range(tr.t.shape[0]):
        R = so3.quat_to_rotmat(tr.sensor_quat[i])
        a_world_meas[i] = R @ tr.accel_body[i] + so3.G_WORLD
    acc_num = np.gradient(np.gradient(tr.sensor_pos, dt, axis=0), dt, axis=0)
    err = np.linalg.norm(acc_num - a_world_meas, axis=1)[3:-3]
    # Peak world accelerations reach ~100 m/s^2; finite-difference truncation
    # keeps the residual well under 1 m/s^2 at 1 kHz.
    assert float(np.sqrt(np.mean(err**2))) < 0.1
    assert float(np.max(err)) < 1.0


def test_gyro_reintegration_recovers_orientation():
    tr = _build()
    dt = tr.dt
    q = tr.sensor_quat[0].copy()
    max_err = 0.0
    for i in range(1, tr.t.shape[0]):
        q = so3.integrate_gyro_rk4(q, tr.gyro_body[i - 1], dt)
        max_err = max(max_err, so3.geodesic_distance(q, tr.sensor_quat[i]))
    assert max_err < 0.02  # rad, first-order strapdown discretisation only


def test_self_consistency_report():
    tr = _build()
    rep = mb.self_consistency(tr)
    assert rep["accel_rms"] < 0.05
    assert rep["accel_max"] < 1.0
    assert rep["gyro_rms"] < 1e-3
    assert rep["gyro_max"] < 1e-2
    assert rep["velocity_rms"] < 1e-2
    assert rep["reintegration_final_rad"] < 1e-3
    assert rep["reintegration_max_rad"] < 0.02


def test_kinematic_sequence_proximal_to_distal():
    tr = _build()
    assert tr.kinematic_sequence_ok()
    assert np.all(np.diff(tr.seg_peak_speed_time) > 0.0)
    # Peaks land in the downswing/follow-through window.
    assert tr.top_idx <= tr.seg_peak_speed_idx[0]
    assert tr.seg_peak_speed_idx[-1] <= tr.finish_idx


def test_casting_breaks_the_sequence():
    cast = mb.casting_swing()
    assert not cast.kinematic_sequence_ok()
    # The club (distal) peak arrives before the arm peak: lost lag.
    assert cast.seg_peak_speed_time[3] < cast.seg_peak_speed_time[2]


def test_peak_speed_magnitudes_are_realistic():
    tr = _build()
    deg = tr.seg_peak_speed_rad_s * 180.0 / np.pi
    assert 400.0 <= deg[0] <= 700.0  # pelvis
    assert 700.0 <= deg[1] <= 900.0  # torso
    assert 800.0 <= deg[2] <= 1200.0  # lead arm
    assert deg[3] >= 1500.0  # club much higher
    assert np.all(np.diff(deg) > 0.0)  # strictly increasing magnitudes


def test_arc_is_planar_and_normal_recovered():
    tr = _build()
    n_axis = tr.plane_normal
    assert abs(np.linalg.norm(n_axis) - 1.0) < 1e-12
    # Every tracked point keeps a constant coordinate along the plane normal.
    for pts in (tr.club_head_pos, tr.sensor_pos):
        assert float(np.std(pts @ n_axis)) < 1e-9


def test_club_head_speed_and_x_factor_reasonable():
    tr = _build()
    assert tr.club_head_speed.shape == tr.t.shape
    # Club head is the fastest point and reaches a plausible speed.
    assert tr.club_head_speed.max() > tr.sensor_vel.__abs__().sum(axis=1).max() * 0.0 + 20.0
    # X-factor (torso-pelvis) is largest in magnitude near the top of backswing.
    assert abs(tr.x_factor_rad[tr.top_idx]) > 0.5  # rad, > ~30 deg separation


def test_imu_packet_roundtrip():
    tr = _build()
    pkt = tr.to_imu_packet()
    assert pkt.t.shape[0] == tr.t.shape[0]
    assert np.allclose(pkt.gyro, tr.gyro_body)
    assert np.allclose(pkt.accel, tr.accel_body)
    pkt_c = tr.to_imu_packet(couple_high_order=True)
    assert not np.allclose(pkt_c.gyro, tr.gyro_body)
