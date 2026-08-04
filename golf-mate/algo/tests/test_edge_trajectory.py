"""Edge trajectory contract + NumPy teacher/student baseline."""

from __future__ import annotations

import numpy as np
import pytest

from golfmate_algo.export.edge_trajectory_contract import (
    CONTRACT_VERSION,
    INPUT_FS_HZ,
    OUTPUT_DIM,
    TRAJECTORY_POINTS,
    EdgeTrajectoryOutput,
    load_edge_trajectory_schema,
    sample_trajectory_xyz,
)
from golfmate_algo.export.edge_trajectory_model import (
    extract_edge_features,
    fit_edge_student,
    load_edge_student,
    resample_to_edge_input,
    teacher_edge_output,
    train_default_edge_student,
)
from golfmate_algo.synth.analytic import planar_circular_swing


def test_edge_schema_matches_constants():
    schema = load_edge_trajectory_schema()
    assert schema["contract_version"] == CONTRACT_VERSION
    assert schema["input"]["fs_hz"] == INPUT_FS_HZ
    assert schema["output"]["trajectory_xyz"]["points"] == TRAJECTORY_POINTS
    assert schema["output"]["output_dim"] == OUTPUT_DIM


def test_teacher_output_shape_and_ranges():
    swing = planar_circular_swing(fs_hz=200.0)
    out = teacher_edge_output(swing.packet, compare_to_ideal=False)
    assert out.version == CONTRACT_VERSION
    assert out.phases_norm.shape == (4,)
    assert out.trajectory_xyz.shape == (TRAJECTORY_POINTS, 3)
    assert 0.0 <= out.phases_norm[0] <= out.phases_norm[1] <= out.phases_norm[2] <= out.phases_norm[3] <= 1.0
    assert 0.05 <= out.confidence <= 0.95
    assert 0.0 <= out.transition_rush <= 1.0
    vec = out.as_vector()
    assert vec.shape == (OUTPUT_DIM,)
    roundtrip = EdgeTrajectoryOutput.from_vector(vec)
    assert np.allclose(roundtrip.trajectory_xyz, out.trajectory_xyz)


def test_edge_input_resamples_to_100hz():
    swing = planar_circular_swing(fs_hz=200.0)
    edge = resample_to_edge_input(swing.packet)
    assert edge.frame.fs_hz == pytest.approx(INPUT_FS_HZ)
    dt = np.diff(edge.t)
    assert np.allclose(dt, 1.0 / INPUT_FS_HZ, rtol=1e-6, atol=1e-9)


def test_student_deterministic_and_predicts():
    a = train_default_edge_student(n_train=8, seed=0)
    b = train_default_edge_student(n_train=8, seed=0)
    assert np.allclose(a.W, b.W)
    assert np.allclose(a.b, b.b)
    assert a.train_seed == 0

    swing = planar_circular_swing(fs_hz=INPUT_FS_HZ, casting=True)
    pred = a.predict(swing.packet)
    assert pred.trajectory_xyz.shape == (TRAJECTORY_POINTS, 3)
    assert pred.as_vector().shape == (OUTPUT_DIM,)
    # Same input → same prediction.
    pred2 = a.predict(swing.packet)
    assert np.allclose(pred.as_vector(), pred2.as_vector())


def test_student_artifact_roundtrip(tmp_path):
    student = train_default_edge_student(n_train=6, seed=1)
    path = student.save(tmp_path / "student.npz")

    loaded = load_edge_student(path)
    swing = planar_circular_swing(fs_hz=INPUT_FS_HZ)
    assert np.allclose(
        student.predict_vector(swing.packet), loaded.predict_vector(swing.packet)
    )


def test_shipped_student_passes_independent_synthetic_trajectory_gate():
    """The bundled model must generalize beyond its deterministic train seed."""
    student = load_edge_student()
    rng = np.random.default_rng(991)
    trajectory_rmse_m: list[float] = []
    phase_mae_s: list[float] = []
    for i in range(24):
        casting = bool(i % 3 == 0)
        swing = planar_circular_swing(
            fs_hz=INPUT_FS_HZ,
            casting=casting,
            casting_lead_s=float(rng.uniform(0.04, 0.15)) if casting else 0.0,
            radius_m=float(rng.uniform(0.38, 0.75)),
            backswing_s=float(rng.uniform(0.60, 0.95)),
            downswing_s=float(rng.uniform(0.18, 0.35)),
            top_angle_deg=float(rng.uniform(90.0, 130.0)),
            plane_tilt_deg=float(rng.uniform(40.0, 70.0)),
            impact_shock_g=float(rng.uniform(1.5, 10.0)),
        )
        prediction = student.predict(swing.packet)
        teacher = teacher_edge_output(swing.packet)
        trajectory_rmse_m.append(
            float(
                np.sqrt(
                    np.mean(
                        np.sum(
                            (prediction.trajectory_xyz - teacher.trajectory_xyz) ** 2,
                            axis=1,
                        )
                    )
                )
            )
        )
        duration = float(swing.packet.t[-1] - swing.packet.t[0])
        phase_mae_s.append(
            float(np.mean(np.abs(prediction.phases_norm - teacher.phases_norm)))
            * duration
        )

    # Teacher-distillation gate. Real optical Watch data remains a separate
    # release gate; this prevents a visibly broken model from entering bundle.
    assert np.mean(trajectory_rmse_m) <= 0.10
    assert np.quantile(trajectory_rmse_m, 0.95) <= 0.17
    assert np.quantile(phase_mae_s, 0.95) <= 0.04


def test_casting_increases_teacher_transition_rush():
    healthy = teacher_edge_output(
        planar_circular_swing(fs_hz=INPUT_FS_HZ, casting=False).packet
    )
    casting = teacher_edge_output(
        planar_circular_swing(
            fs_hz=INPUT_FS_HZ, casting=True, casting_lead_s=0.12
        ).packet
    )
    assert casting.transition_rush >= healthy.transition_rush - 1e-9


def test_sample_trajectory_origin_at_address():
    pos = np.linspace(0, 1, 100).reshape(-1, 1) * np.array([1.0, 2.0, 3.0])
    traj = sample_trajectory_xyz(pos, address_idx=10, finish_idx=90, n_points=64)
    assert traj.shape == (64, 3)
    assert np.allclose(traj[0], 0.0, atol=1e-12)


def test_fit_edge_student_on_two_packets():
    pkts = [
        planar_circular_swing(fs_hz=INPUT_FS_HZ, casting=False).packet,
        planar_circular_swing(fs_hz=INPUT_FS_HZ, casting=True).packet,
    ]
    student = fit_edge_student(pkts, seed=0)
    feats = extract_edge_features(pkts[0])
    assert feats.shape == (len(student.feature_names),)
