"""Tests for zero-trust eval: cross-generator, protocol, gates, multisense."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from golfmate_algo.bench.datasets import multisense as msg
from golfmate_algo.bench.evaluate import run_evaluation
from golfmate_algo.bench.gates import check_gates
from golfmate_algo.bench.harness import build_cases_multibody
from golfmate_algo.bench.protocol import (
    DEFAULT_HOLDOUT_DIR,
    build_protocol_cases,
    seal_holdout,
    verify_holdout_inputs,
)
from golfmate_algo.synth.imu_model import ImuErrorParams


def test_multibody_cases_build():
    cases = build_cases_multibody(
        seeds=(0,),
        error_levels={"consumer": lambda s: ImuErrorParams.consumer_grade(seed=s)},
        violate=False,
    )
    assert len(cases) == 4
    assert cases[0].generator == "multibody"
    assert cases[0].assumptions.get("rigid_fixed_center") is True


def test_violation_cases_flag_assumptions():
    cases = build_cases_multibody(
        seeds=(0,),
        error_levels={"ideal": lambda s: ImuErrorParams.ideal()},
        violate=True,
    )
    assert cases[0].generator == "multibody_violate"
    assert cases[0].assumptions.get("rigid_fixed_center") is False


def test_seal_and_verify_holdout(tmp_path: Path):
    out = tmp_path / "holdout"
    manifest = seal_holdout(out, generators=("analytic", "multibody"))
    assert "artifact_sha256" in manifest
    tracks = build_protocol_cases(
        mode="holdout",
        generators=("analytic", "multibody"),
    )
    # Point verify at tmp sealed dir
    import golfmate_algo.bench.protocol as proto

    old = proto.DEFAULT_HOLDOUT_DIR
    try:
        mismatches = verify_holdout_inputs(tracks, out_dir=out)
    finally:
        pass
    assert mismatches == []


def test_gates_detect_missing_rise():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 10.0}}},
                "e2e": {"consumer": {"position_cm": {"mean": 12.0}}},
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "violation_stress": {
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "external_multisense": {"status": "unavailable", "reason": "test"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 6.0}},
            "gyro_only": {"consumer": {"mean": 50.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = check_gates(payload)
    assert g["pass"] is False
    assert any("residual" in v for v in g["violations"])


def test_gates_detect_position_budget():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 10.0}}},
                "e2e": {
                    "consumer": {
                        "position_cm": {"mean": 22.0},
                        "orientation_deg": {"mean": 4.0},
                    }
                },
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "violation_stress": {
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 10.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "external_multisense": {"status": "unavailable", "reason": "test"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 6.0}},
            "gyro_only": {"consumer": {"mean": 50.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = check_gates(payload)
    assert g["pass"] is False
    assert any("17 cm" in v for v in g["violations"])


def test_gates_detect_orientation_budget():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 5.0}}},
                "e2e": {
                    "consumer": {
                        "position_cm": {"mean": 10.0},
                        "orientation_deg": {"mean": 12.0},
                    }
                },
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 5.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "violation_stress": {
                "trajectory": {
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 10.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "external_multisense": {"status": "unavailable", "reason": "test"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 6.0}},
            "gyro_only": {"consumer": {"mean": 50.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = check_gates(payload)
    assert g["pass"] is False
    assert any("8°" in v for v in g["violations"])


def test_evaluate_quick_dual_track():
    payload = run_evaluation(
        mode="dev",
        n_boot=100,
        quick=True,
        include_multisense=True,
        include_degradation=False,
        n_dev=1,
    )
    assert "by_track" in payload
    assert "cross_multibody" in payload["by_track"]
    assert "violation_stress" in payload["by_track"]
    assert "isomorphic_analytic" in payload["by_track"]
    assert "gates" in payload
    cross = payload["by_track"]["cross_multibody"]
    assert "e2e" in cross
    assert cross["credibility"] == "cross_generator_accurate"


@pytest.mark.skipif(not msg.dataset_status()["ready"], reason="MultiSenseGolf not extracted")
def test_multisense_smoke():
    cases = list(msg.iter_local_swings(max_swings=2))
    assert len(cases) >= 1
    c = cases[0]
    assert c.packet.gyro.shape[0] > 10
    assert 0 <= c.impact_idx < c.packet.gyro.shape[0]
    # Physical sanity after adapter repair
    peak = float(np.max(np.linalg.norm(c.packet.gyro, axis=1)))
    assert peak > 5.0  # rad/s — deg2rad bug would leave this ~0.1
    rest_a = float(np.mean(np.linalg.norm(c.packet.accel[:5], axis=1)))
    assert 7.0 < rest_a < 12.5  # ~g after Y-up→Z-up
    # Z-up: hand height mostly in Z
    assert float(np.median(c.positions_ref[:, 2])) > 0.5
    # Fixed-rate grid
    dts = np.diff(c.packet.t)
    assert float(np.std(dts) / np.median(dts)) < 0.02


@pytest.mark.skipif(not msg.dataset_status()["ready"], reason="MultiSenseGolf not extracted")
def test_multisense_pipeline_orientation_bound():
    from golfmate_algo.bench.evaluate import _yaw_align
    from golfmate_algo.bench.harness import orientation_error_deg
    from golfmate_algo.pipeline import analyze_swing

    case = next(msg.iter_local_swings(max_swings=1))
    report = analyze_swing(case.packet)
    nq = min(report.quats.shape[0], case.quats_ref.shape[0])
    aligned = _yaw_align(report.quats[:nq], case.quats_ref[:nq], 0)
    err = float(np.mean(orientation_error_deg(aligned, case.quats_ref[:nq])))
    assert err < 35.0
    assert report.meta.get("impact_mode") in {
        "collision",
        "kinematic_proxy",
        "unavailable",
    }
