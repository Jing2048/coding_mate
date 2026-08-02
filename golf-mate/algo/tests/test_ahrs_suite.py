"""Tests for the production AHRS benchmark suite."""

from __future__ import annotations

import numpy as np

from golfmate_algo.ahrs import (
    EKFOrientation,
    Complementary,
    GatedAdaptive,
    GyroOnly,
    MadgwickAHRS,
    MahonyAHRS,
    estimate_address_orientation,
    forward_backward_filter_smooth,
    make_default_suite,
    rest_detection,
    rts_smooth_orientations,
)
from golfmate_algo.math import so3


def _static_samples(n: int = 100) -> tuple[np.ndarray, np.ndarray]:
    gyro = np.zeros((n, 3), dtype=np.float64)
    accel = np.tile(np.array([0.0, 0.0, 9.80665], dtype=np.float64), (n, 1))
    return gyro, accel


def test_estimate_address_orientation_level_static_identity() -> None:
    gyro, accel = _static_samples(80)
    q0, win, metrics = estimate_address_orientation(gyro, accel, fs=200.0)
    assert win.stop > win.start
    assert metrics["quality"] == "good"
    assert metrics["rest_fraction"] > 0.8
    assert so3.geodesic_distance(q0, [1.0, 0.0, 0.0, 0.0]) < 1e-8


def test_rest_detection_finds_static_and_rejects_spike() -> None:
    gyro, accel = _static_samples(100)
    gyro[45:55, 0] = 4.0
    accel[70:75, 2] = 25.0
    mask = rest_detection(gyro, accel, fs=200.0)
    assert mask[:30].mean() > 0.8
    assert not mask[48]
    assert not mask[72]


def test_all_suite_filters_return_finite_unit_quats() -> None:
    n = 60
    dt = 0.005
    gyro = np.zeros((n, 3), dtype=np.float64)
    gyro[:, 2] = 1.0
    accel = np.tile(np.array([0.0, 0.0, 9.80665], dtype=np.float64), (n, 1))
    accel[20, :] = np.nan

    for estimator in make_default_suite():
        quats, diag = estimator.run(gyro, accel, dt)
        assert quats.shape == (n, 4), estimator.name
        assert np.all(np.isfinite(quats)), estimator.name
        assert np.max(np.abs(np.linalg.norm(quats, axis=1) - 1.0)) < 1e-10, estimator.name
        assert isinstance(diag, dict), estimator.name


def test_complementary_corrects_static_tilt() -> None:
    gyro, accel = _static_samples(250)
    q_bad = so3.quat_from_axis_angle([1.0, 0.0, 0.0], np.deg2rad(20.0))
    est = Complementary(gain=8.0)
    quats, _ = est.run(gyro, accel, 1.0 / 200.0, q0=q_bad)
    assert so3.geodesic_distance(quats[-1], [1.0, 0.0, 0.0, 0.0]) < np.deg2rad(4.0)


def test_adaptive_gain_smoothly_drops_in_high_dynamics() -> None:
    est = GatedAdaptive(tilt_gain=3.0, sigma_a=2.0, sigma_w=3.0)
    est.reset()
    est.update([0.0, 0.0, 0.0], [0.0, 0.0, 9.80665], 0.005)
    est.update([8.0, 0.0, 0.0], [0.0, 0.0, 25.0], 0.005)
    diag = est.diagnostics()
    gains = diag["gain_history"]
    assert gains[0] > gains[1]
    assert 0.0 <= gains[1] < gains[0]


def test_ekf_inflates_accel_noise_when_norm_is_bad() -> None:
    est = EKFOrientation(accel_sigma=2.0)
    est.reset()
    est.update([0.0, 0.0, 0.0], [0.0, 0.0, 9.80665], 0.005)
    est.update([0.0, 0.0, 0.0], [0.0, 0.0, 25.0], 0.005)
    scales = est.diagnostics()["measurement_noise_scale"]
    assert scales[1] > scales[0]


def test_smoothers_preserve_shape_and_unit_norm() -> None:
    gyro, accel = _static_samples(30)
    quats, _ = GyroOnly().run(gyro, accel, 0.005)
    smooth = rts_smooth_orientations(quats, alpha=0.5)
    assert smooth.shape == quats.shape
    assert np.max(np.abs(np.linalg.norm(smooth, axis=1) - 1.0)) < 1e-12

    fb, diag = forward_backward_filter_smooth(lambda: Complementary(gain=1.0), gyro, accel, 0.005)
    assert fb.shape == quats.shape
    assert diag["method"] == "forward_backward_filter_smooth"
    assert np.max(np.abs(np.linalg.norm(fb, axis=1) - 1.0)) < 1e-12


def test_named_estimators_can_be_constructed_individually() -> None:
    estimators = [
        GyroOnly(),
        Complementary(),
        MahonyAHRS(),
        MadgwickAHRS(),
        EKFOrientation(),
        GatedAdaptive(),
    ]
    assert [est.name for est in estimators] == [
        "gyro_only",
        "complementary",
        "mahony",
        "madgwick",
        "ekf_orientation",
        "gated_adaptive",
    ]
