"""Robust golden-eval coverage: catalog, CMU64, MultiSense strata, synth regimes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from golfmate_algo.bench.datasets import cmu64, wit_kinnet
from golfmate_algo.bench.datasets import multisense as msg
from golfmate_algo.bench.evaluate import run_evaluation
from golfmate_algo.bench.gates import check_gates as gates_fn
from golfmate_algo.bench.golden.catalog import ranked_catalog
from golfmate_algo.bench.golden import scirep_budgets
from golfmate_algo.bench.harness import build_cases_robust_golden
from golfmate_algo.bench.protocol import build_protocol_cases
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.imu_model import ImuErrorParams


def test_golden_catalog_ranks_commercial_sources_first():
    cat = ranked_catalog()
    assert cat[0].name == "MultiSenseGolf"
    assert cat[0].commercial_eval_ok
    assert any(s.name.startswith("CMU") for s in cat)
    assert scirep_budgets.POSITION_CM_WHOLE_SWING == 17.0


def test_robust_golden_cases_cover_regimes():
    tracks = build_cases_robust_golden(
        seeds=(0,),
        error_levels={"consumer": lambda s: ImuErrorParams.consumer_grade(seed=s)},
    )
    assert set(tracks) >= {
        "pro_regime",
        "casting_pathology",
        "fs_stress",
        "clip_stress",
        "lefty_mirror",
    }
    assert tracks["casting_pathology"][0].assumptions.get("mount_segment") == 3.0
    assert tracks["pro_regime"][0].assumptions.get("rigid_fixed_center") is False
    fs_labels = {c.label for c in tracks["fs_stress"]}
    assert any("50hz" in x for x in fs_labels)
    assert any("100hz" in x for x in fs_labels)
    assert tracks["clip_stress"][0].assumptions.get("gyro_saturated_frac", 0) >= 0.0


def test_protocol_includes_robust_without_breaking_core():
    tracks = build_protocol_cases(
        mode="dev",
        n_dev=1,
        generators=("multibody", "robust_golden"),
        error_levels={"consumer": lambda s: ImuErrorParams.consumer_grade(seed=s)},
    )
    assert "cross_multibody" in tracks
    assert "pro_regime" in tracks


def test_lefty_robust_case_runs_pipeline():
    tracks = build_cases_robust_golden(
        seeds=(0,),
        error_levels={"consumer": lambda s: ImuErrorParams.consumer_grade(seed=s)},
    )
    case = tracks["lefty_mirror"][0]
    report = analyze_swing(case.swing.packet)
    assert report.phases.impact_idx > report.phases.top_idx


def test_cmu64_parser_and_pipeline():
    st = cmu64.dataset_status()
    if not st["ready"]:
        pytest.skip("CMU64 raw ASF/AMC not present")
    cases = list(cmu64.iter_local_swings(max_swings=1))
    assert cases
    case = cases[0]
    assert case.packet.gyro.shape[0] > 50
    assert case.adapter_meta["peak_omega_rad_s"] > 1.0
    assert case.adapter_meta["path_span_m"] > 0.05
    report = analyze_swing(case.packet)
    assert np.isfinite(report.features.tempo_s)


def test_multisense_high_speed_filter():
    st = msg.dataset_status()
    if not st["ready"]:
        pytest.skip("MultiSense not extracted")
    all_n = sum(1 for _ in msg.iter_local_swings(max_swings=40))
    hi = list(msg.iter_local_swings(max_swings=40, club_speed_min_m_s=20.0))
    assert all_n >= len(hi)
    for c in hi:
        assert c.reference.get("club_speed_m_s", 0) >= 20.0


def test_wit_kinnet_stub_not_ready():
    st = wit_kinnet.dataset_status()
    assert st["ready"] is False
    assert "contract" in st
    assert st["contract"]["contract_version"].startswith("wit-kinnet")


def test_elite_manifest_resolves_and_lists_subjects():
    from golfmate_algo.reference.elite import elite_subject_ids, load_elite_manifest

    m = load_elite_manifest()
    assert m.get("status") != "missing_manifest"
    ids = elite_subject_ids()
    assert "Sub13" in ids and "Sub19" in ids and "Sub24" in ids
    assert Path(m["resolved_path"]).exists()


def test_multisense_elite_filter_when_extracted():
    st = msg.dataset_status()
    if not st["ready"]:
        pytest.skip("MultiSense not extracted")
    from golfmate_algo.reference.elite import elite_subject_ids

    elite = elite_subject_ids()
    available = set(st.get("subjects_extracted", []))
    elite_local = [s for s in elite if s in available]
    if not elite_local:
        pytest.skip("elite subjects not extracted locally")
    cases = list(msg.iter_local_swings(max_swings=5, subjects=elite_local))
    assert cases
    for c in cases:
        assert c.subject_id in elite_local


def test_optical_aligned_protocol_twin():
    from golfmate_algo.bench.datasets import optical_aligned as oa

    st = oa.dataset_status()
    assert st["ready"] is True
    assert st["fs_hz"] == 200.0
    cases = list(oa.iter_local_swings(max_swings=3))
    assert len(cases) == 3
    case = cases[0]
    assert case.packet.frame.fs_hz == pytest.approx(200.0, abs=1e-6)
    assert case.provenance.startswith("inhouse_optical_aligned")
    assert case.quats_ref.shape[0] == case.packet.t.shape[0]
    report = analyze_swing(case.packet)
    assert report.phases.impact_idx > report.phases.top_idx
    paths = oa.materialize(max_swings=2)
    assert paths and paths[0].exists()


def test_wit_kinnet_contract_readme():
    path = wit_kinnet.write_contract_readme()
    assert path.exists()
    assert "wit-kinnet-contract-v1" in path.read_text(encoding="utf-8")


def test_gates_elite_and_optical_ceilings():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 8.0}}},
                "e2e": {
                    "consumer": {
                        "position_cm": {"mean": 12.0},
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
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 8.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "external_multisense_elite": {
                "status": "ok",
                "n_swings": 10,
                "subjects_filter": ["Sub13"],
                "orientation_deg": {"mean": 12.0},
                "position_cm": {"mean": 70.0},
            },
            "external_optical_aligned": {
                "status": "ok",
                "n_swings": 4,
                "protocol_fs_hz": 200.0,
                "orientation_deg": {"mean": 12.0},
                "impact_ms": {"mean": 120.0},
                "position_cm": {"mean": 80.0},
            },
            "external_wit_kinnet": {
                "status": "unavailable",
                "reason": "pending author share",
            },
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 5.0}},
            "gyro_only": {"consumer": {"mean": 40.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = gates_fn(payload)
    assert g["pass"] is True
    assert any("elite" in n for n in g["notes"])
    assert any("optical_aligned" in n for n in g["notes"])


def test_gates_robust_track_budgets():
    payload = {
        "by_track": {
            "cross_multibody": {
                "events": {"impact": {"consumer": {"mean": 8.0}}},
                "e2e": {
                    "consumer": {
                        "position_cm": {"mean": 12.0},
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
                    "lever_arm_residual_m_s2": {"consumer": {"mean": 8.0}},
                    "lever_arm_invalid": {"consumer": {"mean": 0.0}},
                },
            },
            "pro_regime": {
                "e2e": {
                    "consumer": {
                        "orientation_deg": {"mean": 5.0},
                        "impact_ms": {"mean": 10.0},
                        "position_cm": {"mean": 15.0},
                    }
                }
            },
            "external_multisense": {"status": "unavailable"},
            "external_cmu64": {"status": "unavailable"},
        },
        "session": {
            "gated_adaptive": {"consumer": {"mean": 5.0}},
            "gyro_only": {"consumer": {"mean": 40.0}},
        },
        "meta": {"disclaimer_isomorphic_upper_bound": True},
        "holdout": {"enabled": False},
    }
    g = gates_fn(payload)
    assert g["pass"] is True


def test_quick_eval_includes_robust_tracks():
    payload = run_evaluation(
        mode="dev",
        quick=True,
        n_dev=1,
        include_multisense=False,
        include_degradation=False,
        generators=["robust_golden"],
    )
    assert "pro_regime" in payload["by_track"]
    assert "casting_pathology" in payload["by_track"]
    assert "lefty_mirror" in payload["by_track"]
    assert "external_optical_aligned" in payload["by_track"]
    assert payload["by_track"]["external_optical_aligned"]["status"] == "ok"
    # Robust-only run should not trip cross_multibody product gates.
    lefty = payload["by_track"]["lefty_mirror"]["e2e"]["consumer"]
    assert lefty["orientation_deg"]["mean"] < 15.0
    assert lefty["position_cm"]["mean"] < 35.0
    assert payload["gates"]["pass"] is True
