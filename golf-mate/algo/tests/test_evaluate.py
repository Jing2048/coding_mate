"""Smoke tests for the evaluation suite."""

from __future__ import annotations

from golfmate_algo.bench.ablation import (
    benchmark_degradation,
    benchmark_gate_ablation,
)
from golfmate_algo.bench.evaluate import run_evaluation
from golfmate_algo.bench.harness import build_cases
from golfmate_algo.bench.stats import bootstrap_ci, summarize


def test_bootstrap_ci_covers_mean():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    mean, lo, hi = bootstrap_ci(vals, n_boot=500, seed=0)
    assert lo <= mean <= hi
    s = summarize(vals, n_boot=500, seed=0)
    assert s.n == 5
    assert s.ci95_lo <= s.mean <= s.ci95_hi


def test_gate_ablation_smoke():
    cases = build_cases(seeds=(0,))
    cases = [c for c in cases if c.error_label == "consumer"]
    out = benchmark_gate_ablation(cases, n_boot=200)
    assert "full_gate+rest" in out
    assert "gyro_only" in out
    assert "consumer/all" in out["full_gate+rest"]


def test_degradation_smoke():
    out = benchmark_degradation(scales=[0.0, 1.0], seeds=(0, 1), n_boot=100)
    assert len(out["single_swing"]) == 2
    assert out["single_swing"][0]["scale"] == 0.0


def test_evaluate_quick():
    payload = run_evaluation(
        mode="dev",
        n_boot=100,
        quick=True,
        include_multisense=False,
        include_degradation=False,
        n_dev=1,
    )
    assert "by_track" in payload
    assert "gates" in payload
    cross = payload["by_track"]["cross_multibody"]
    assert cross["e2e"]
    cons = cross["e2e"].get("consumer")
    assert cons is not None
    assert cons["orientation_deg"]["n"] >= 1
