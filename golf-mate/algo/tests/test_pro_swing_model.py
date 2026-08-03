"""Professional swing model layer tests."""

from __future__ import annotations

import numpy as np

from golfmate_algo.biomechanics.wrist_channels import estimate_segment_channels
from golfmate_algo.model.elite_manifold import build_default_manifold, score_against_manifold
from golfmate_algo.model.phase_normalize import concatenate_phases, phase_normalize
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.multibody import SwingConfig, build_swing, casting_swing, pro_sequence_swing


def test_segment_channels_address_zero():
    truth = build_swing(SwingConfig(plane_tilt_deg=50.0))
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    ch = estimate_segment_channels(
        report.quats,
        pkt.gyro,
        1.0 / pkt.frame.fs_hz,
        address_idx=report.phases.address_idx,
    )
    a = report.phases.address_idx
    assert abs(ch.twist_rad[a]) < 1e-6
    assert abs(ch.swing_rad[a]) < 1e-6
    assert ch.is_proxy


def test_phase_normalize_preserves_impact_boundary():
    truth = build_swing(SwingConfig(plane_tilt_deg=55.0))
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    omega = np.linalg.norm(pkt.gyro, axis=1)
    normed = phase_normalize(pkt.t, omega, report.phases, channel_names=("omega",))
    assert normed.validity
    assert normed.grids["top_to_impact"].shape[0] == 32
    assert normed.phase_durations_s["top_to_impact"] > 0.04
    flat = concatenate_phases(normed)
    assert flat.shape[0] == 48 + 32 + 32


def test_release_profile_and_pro_report():
    truth = build_swing(SwingConfig())
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    assert "pro_swing" in report.meta
    pro = report.meta["pro_swing"]
    assert pro["release"]["is_proxy"] is True
    assert pro["release"]["morphology"] in {
        "early",
        "gradual",
        "late",
        "abrupt",
        "unclear",
    }
    assert "phase_durations_s" in pro


def test_casting_mount_observes_club_release():
    """Casting must mount distal so club peak timing is visible on the IMU."""
    cast = casting_swing(SwingConfig())
    assert cast.config.mount_segment == 3
    assert not cast.kinematic_sequence_ok()


def test_pro_sequence_has_translating_center():
    truth = pro_sequence_swing(sway_m=0.05, lift_m=0.02)
    assert truth.meta["center_sway_amp_m"] == 0.05
    assert truth.meta["center_path_span_m"] > 0.03
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    assert report.phases.impact_idx > report.phases.top_idx


def test_manifold_fit_and_score(tmp_path):
    path = tmp_path / "pro_manifold.json"
    man = build_default_manifold(n_swings=8, seed=0, path=path)
    assert path.exists()
    assert man.n_train == 8
    truth = build_swing(SwingConfig(plane_tilt_deg=48.0))
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    ch = estimate_segment_channels(
        report.quats, pkt.gyro, 1.0 / pkt.frame.fs_hz, address_idx=report.phases.address_idx
    )
    omega = np.linalg.norm(pkt.gyro, axis=1)
    mat = np.column_stack(
        [omega, ch.twist_rate_rad_s, ch.omega_plane_rad_s, ch.twist_rad]
    )
    normed = phase_normalize(
        pkt.t,
        mat,
        report.phases,
        channel_names=("omega", "twist_rate", "plane_rate", "twist"),
        grid_sizes=man.grid_sizes,
    )
    score = score_against_manifold(normed, manifold=man)
    assert score is not None
    assert score.pca_score >= 0.0
    assert score.is_proxy


def test_pro_sequence_lag_proxy_and_refine_meta():
    truth = pro_sequence_swing(sway_m=0.05, lift_m=0.02)
    pkt = truth.to_imu_packet()
    report = analyze_swing(pkt, compare_to_ideal=False)
    seq = report.meta["sequence_proxy"]
    assert "lag_proxy_s" in seq
    assert np.isfinite(seq["lag_proxy_s"])
    # High peak rates should engage pro event refine path
    assert "pro_refine_applied" in report.meta or report.meta.get("pro_refine_applied") in (
        0.0,
        1.0,
    )
