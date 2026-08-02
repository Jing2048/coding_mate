"""AHRS analytic and gate tests."""

from __future__ import annotations

import numpy as np

from golfmate_algo.ahrs.gated_vqf import (
    ComplementaryGatedAHRS,
    GateParams,
    GolfGatedAHRS,
    gravity_remove,
)
from golfmate_algo.math import so3
from golfmate_algo.synth.analytic import constant_rate_rotation


def test_gravity_removal_static_near_zero():
    q = np.array([[1.0, 0.0, 0.0, 0.0]])
    accel = np.array([[0.0, 0.0, 9.80665]])
    lin = gravity_remove(q, accel)
    assert np.linalg.norm(lin) < 1e-8


def test_complementary_tracks_constant_rate_rotation():
    truth = constant_rate_rotation(fs_hz=200.0, duration_s=0.5, rate_rad_s=1.2)
    dt = 1.0 / truth.packet.frame.fs_hz
    ahrs = ComplementaryGatedAHRS(
        GateParams(accel_tol_g=0.15, omega_hi_rad_s=0.5, kp_tilt=1.0)
    )
    # High omega → gate closed → pure gyro integration should match truth
    quats, gate = ahrs.batch_process(truth.packet.gyro, truth.packet.accel, dt)
    assert np.mean(gate) < 0.2  # mostly gated off due to omega
    errs = [
        so3.geodesic_distance(quats[i], truth.quats_true[i])
        for i in range(len(quats))
    ]
    assert max(errs) < np.deg2rad(2.0)


def test_gate_closes_on_impact_spike():
    ahrs = ComplementaryGatedAHRS(GateParams(accel_tol_g=0.2, omega_hi_rad_s=5.0))
    dt = 0.005
    # Static-ish
    ahrs.update([0.0, 0.0, 0.0], [0.0, 0.0, 9.8], dt)
    assert ahrs.gate_open_history[-1] == 1.0
    # Impact-like accel
    ahrs.update([0.0, 0.0, 0.0], [0.0, 0.0, 40.0], dt)
    assert ahrs.gate_open_history[-1] == 0.0


def test_golf_gated_facade_batch():
    truth = constant_rate_rotation(duration_s=0.2, rate_rad_s=0.8)
    dt = 1.0 / truth.packet.frame.fs_hz
    ahrs = GolfGatedAHRS(fs_hz=truth.packet.frame.fs_hz, prefer_vqf=True)
    quats, gate = ahrs.batch_process(truth.packet.gyro, truth.packet.accel, dt)
    assert quats.shape == truth.quats_true.shape
    assert gate.shape[0] == quats.shape[0]
    assert ahrs.backend_name in {"vqf6d", "complementary"}
