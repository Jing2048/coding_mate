"""Phase, trajectory, plane, features, diagnostics, e2e pipeline tests."""

from __future__ import annotations

import numpy as np
import pytest

from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.events.phase import detect_phases
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.swing_plane import fit_swing_plane
from golfmate_algo.types import WristFeatures


def test_phase_detection_on_synthetic_swing():
    syn = planar_circular_swing(fs_hz=200.0, casting=False)
    phases = detect_phases(syn.packet.t, syn.packet.gyro, syn.packet.accel)
    # Allow ±8 samples @200Hz (=40ms) for Address/Top/Finish; impact a bit looser
    # Tolerances @200Hz: address/top ~50ms, impact ~100ms (spike localization), finish ~80ms
    assert abs(phases.address_idx - syn.phases_true.address_idx) <= 12
    assert abs(phases.top_idx - syn.phases_true.top_idx) <= 16
    assert abs(phases.impact_idx - syn.phases_true.impact_idx) <= 25
    assert abs(phases.finish_idx - syn.phases_true.finish_idx) <= 20
    phases.validate_order()


@pytest.mark.parametrize("tilt_deg", [45.0, 55.0, 70.0])
def test_swing_plane_recovers_geometry(tilt_deg: float):
    syn = planar_circular_swing(radius_m=0.5, plane_tilt_deg=tilt_deg)
    mask = np.zeros(len(syn.packet.t), dtype=bool)
    a, f = syn.phases_true.address_idx, syn.phases_true.finish_idx
    mask[a : f + 1] = True
    plane = fit_swing_plane(syn.positions_true, mask=mask)
    assert abs(plane.radius - 0.5) < 0.05
    assert plane.plane_residual_rms < 0.02
    assert plane.circle_residual_rms < 0.05
    # plane_angle_deg is the tilt of the plane away from horizontal
    assert abs(plane.plane_angle_deg - tilt_deg) < 3.0


def test_zupt_reduces_endpoint_velocity():
    syn = planar_circular_swing()
    dt = 1.0 / syn.packet.frame.fs_hz
    # Use true quats for clean gravity removal
    _, vel_raw, _ = reconstruct_trajectory(
        syn.quats_true, syn.packet.accel, dt, phases=None
    )
    _, vel_z, _ = reconstruct_trajectory(
        syn.quats_true, syn.packet.accel, dt, phases=syn.phases_true
    )
    # At finish, ZUPT should drive velocity near zero vs unconstrained drift
    assert np.linalg.norm(vel_z[syn.phases_true.finish_idx]) < np.linalg.norm(
        vel_raw[syn.phases_true.finish_idx]
    ) + 1e-9
    assert np.linalg.norm(vel_z[syn.phases_true.finish_idx]) < 0.5


def test_casting_diagnostic_triggers():
    """Casting rule is defined on features; validate with ground-truth phases."""
    syn = planar_circular_swing(casting=True, backswing_s=0.8, downswing_s=0.35)
    from golfmate_algo.features.wrist import compute_wrist_features
    from golfmate_algo.traj.dead_reckon import reconstruct_trajectory

    dt = 1.0 / syn.packet.frame.fs_hz
    _, vel, pos = reconstruct_trajectory(
        syn.quats_true, syn.packet.accel, dt, phases=syn.phases_true
    )
    feats = compute_wrist_features(
        syn.packet.t,
        syn.packet.gyro,
        syn.quats_true,
        vel,
        pos,
        syn.phases_true,
    )
    assert feats.peak_omega_to_impact_s > 0.08
    codes = {f.code for f in diagnose(feats)}
    assert "casting_proxy" in codes

    # Pipeline still produces a complete report on the same packet
    report = analyze_swing(syn.packet, prefer_vqf=False)
    assert report.quats.shape[0] == syn.packet.t.shape[0]
    assert report.features.tempo_s > 0


def test_metrics_invariants_normal_swing():
    syn = planar_circular_swing(casting=False, backswing_s=0.75, downswing_s=0.25)
    report = analyze_swing(syn.packet, prefer_vqf=False)
    f = report.features
    assert f.tempo_s > 0
    assert f.backswing_s > 0 and f.downswing_s > 0
    assert f.rhythm > 1.0
    assert f.peak_omega_rad_s > 0
    assert report.phases.address_idx < report.phases.top_idx
    assert report.phases.top_idx < report.phases.impact_idx


def test_pipeline_e2e_schema():
    syn = planar_circular_swing()
    report = analyze_swing(syn.packet, prefer_vqf=True)
    assert report.quats.shape[0] == syn.packet.t.shape[0]
    assert report.positions.shape == (syn.packet.t.shape[0], 3)
    assert report.gate_open.shape[0] == syn.packet.t.shape[0]
    assert isinstance(report.features, WristFeatures)
    assert len(report.findings) >= 1
    assert "backend" in report.meta


def test_diagnose_rhythm_bands():
    base = WristFeatures(
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
    assert any(f.code == "rhythm_ok" for f in diagnose(base))
    fast = WristFeatures(**{**base.__dict__, "rhythm": 1.2})
    assert any(f.code == "rhythm_too_fast_backswing" for f in diagnose(fast))
