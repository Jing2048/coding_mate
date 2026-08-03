"""Zero-trust evaluation runner: dual-track Monte-Carlo + external gate.

Usage
-----
    python -m golfmate_algo.bench.evaluate --mode full
    python -m golfmate_algo.bench.evaluate --mode holdout
    python -m golfmate_algo.bench.evaluate --quick

Tracks
------
* isomorphic_analytic — upper bound only (shares rigid-centre assumption)
* cross_multibody — accurate synthetic numbers (independent generator)
* violation_stress — assumption-breaking; residual / invalid must rise
* external_multisense — MultiSenseGolf mocap-derived wrist IMU (when present)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs import suite as ahrs_suite
from golfmate_algo.bench.ablation import benchmark_degradation
from golfmate_algo.bench.datasets import cmu64, multisense as msg
from golfmate_algo.bench.datasets import wit_kinnet
from golfmate_algo.bench.gates import check_gates
from golfmate_algo.bench.golden.catalog import ranked_catalog
from golfmate_algo.bench.golden import scirep_budgets
from golfmate_algo.bench.harness import (
    SwingCase,
    orientation_error_deg,
    _yaw_align,
)
from golfmate_algo.bench.protocol import (
    Mode,
    PROTOCOL_ID,
    build_protocol_cases,
    load_holdout_manifest,
    protocol_meta,
    seal_holdout,
    verify_holdout_inputs,
)
from golfmate_algo.bench.stats import Summary, summarize
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.math import so3
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.session import make_session
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.hybrid import estimate_hybrid_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.types import ImuPacket


def _sum_dict(s: Summary) -> dict[str, Any]:
    return s.to_dict()


def _yaw_rotate_positions(pos: Any, q_est: Any, q_true: Any, address_idx: int) -> Any:
    aligned = _yaw_align(q_est, q_true, address_idx)
    r = so3.quat_multiply(aligned[address_idx], so3.quat_conjugate(q_est[address_idx]))
    R = so3.quat_to_rotmat(r)
    out = (R @ np.asarray(pos, dtype=np.float64).T).T
    return out - out[address_idx]


# --------------------------------------------------------------------------- track scorers


def _score_orientation(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    case_means: dict[tuple[str, str], list[float]] = {}
    case_means_down: dict[tuple[str, str], list[float]] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        bias, _ = ahrs_init.estimate_gyro_bias(case.gyro, case.accel, fs)
        ph = case.swing.phases_true
        runs: list[tuple[str, Any]] = []
        for est in ahrs_suite.make_default_suite():
            quats, _ = est.run(case.gyro, case.accel, dt, q0=q0)
            runs.append((est.name, quats))
        quats_rb, _ = ahrs_suite.GyroOnly().run(case.gyro - bias, case.accel, dt, q0=q0)
        runs.append(("gyro_only+restbias", quats_rb))
        for name, quats in runs:
            n = min(quats.shape[0], case.swing.quats_true.shape[0])
            aligned = _yaw_align(quats[:n], case.swing.quats_true[:n], ph.address_idx)
            err = orientation_error_deg(aligned, case.swing.quats_true[:n])
            key = (name, case.error_label)
            case_means.setdefault(key, []).append(float(np.mean(err)))
            lo = min(ph.top_idx, n - 1)
            hi = min(ph.impact_idx + 1, n)
            case_means_down.setdefault(key, []).append(float(np.mean(err[lo:hi])))

    out: dict[str, Any] = {"per_swing": {}}
    for (alg, cond), vals in sorted(case_means.items()):
        out["per_swing"].setdefault(alg, {})[f"{cond}/all"] = _sum_dict(
            summarize(vals, n_boot=n_boot, seed=abs(hash((alg, cond))) % 10_000)
        )
        out["per_swing"][alg][f"{cond}/down"] = _sum_dict(
            summarize(
                case_means_down[(alg, cond)],
                n_boot=n_boot,
                seed=abs(hash((alg, cond, "d"))) % 10_000,
            )
        )
    return out


def _score_trajectory(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = {}
    residual: dict[str, list[float]] = {}
    invalid: dict[str, list[float]] = {}
    radius: dict[str, list[float]] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        bias, _ = ahrs_init.estimate_gyro_bias(case.gyro, case.accel, fs)
        gyro_c = case.gyro - bias
        quats, _ = ahrs_suite.GatedAdaptive().run(gyro_c, case.accel, dt, q0=q0)
        n = min(quats.shape[0], case.swing.quats_true.shape[0])
        quats = _yaw_align(quats[:n], case.swing.quats_true[:n], case.swing.phases_true.address_idx)
        ph = case.swing.phases_true
        truth = case.swing.positions_true[:n] - case.swing.positions_true[ph.address_idx]
        window = slice(ph.address_idx, min(ph.finish_idx + 1, n))

        _, _, pos_dr = reconstruct_trajectory(quats, case.accel[:n], dt, phases=ph)
        pos_dr = pos_dr - pos_dr[ph.address_idx]
        e_dr = float(np.mean(np.linalg.norm(pos_dr[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("dead_reckon_zupt", case.error_label), []).append(e_dr)

        la = estimate_lever_arm(quats, gyro_c[:n], case.accel[:n], dt)
        pos_la = la.positions - la.positions[ph.address_idx]
        e_la = float(np.mean(np.linalg.norm(pos_la[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("lever_arm", case.error_label), []).append(e_la)
        residual.setdefault(case.error_label, []).append(float(la.residual_rms_m_s2))
        invalid.setdefault(case.error_label, []).append(0.0 if la.valid else 1.0)
        if case.assumptions.get("rigid_fixed_center", True):
            radius.setdefault(case.error_label, []).append(
                abs(la.radius_m - float(case.swing.meta.get("radius_m", la.radius_m))) * 100.0
            )

        hy = estimate_hybrid_trajectory(
            quats, gyro_c[:n], case.accel[:n], dt, ph
        )
        pos_hy = hy.positions - hy.positions[ph.address_idx]
        e_hy = float(np.mean(np.linalg.norm(pos_hy[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("hybrid", case.error_label), []).append(e_hy)

    out: dict[str, Any] = {
        "position_cm": {},
        "lever_arm_residual_m_s2": {},
        "lever_arm_invalid": {},
        "radius_err_cm": {},
    }
    for (alg, cond), vals in sorted(buckets.items()):
        out["position_cm"].setdefault(alg, {})[cond] = _sum_dict(
            summarize(vals, n_boot=n_boot, seed=21)
        )
    for cond, vals in sorted(residual.items()):
        out["lever_arm_residual_m_s2"][cond] = _sum_dict(
            summarize(vals, n_boot=n_boot, seed=22)
        )
    for cond, vals in sorted(invalid.items()):
        out["lever_arm_invalid"][cond] = _sum_dict(summarize(vals, n_boot=n_boot, seed=23))
    for cond, vals in sorted(radius.items()):
        out["radius_err_cm"][cond] = _sum_dict(summarize(vals, n_boot=n_boot, seed=24))
    return out


def _score_events(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = {}
    failures: dict[str, int] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        try:
            det = detect_phases_segmental(case.t, case.gyro, case.accel)
        except Exception:
            failures[case.error_label] = failures.get(case.error_label, 0) + 1
            continue
        tr = case.swing.phases_true
        for name in ("address", "top", "impact", "finish"):
            err_ms = abs(getattr(det, f"{name}_idx") - getattr(tr, f"{name}_idx")) / fs * 1000.0
            buckets.setdefault((name, case.error_label), []).append(err_ms)
    out: dict[str, Any] = {}
    for (name, cond), vals in sorted(buckets.items()):
        d = _sum_dict(summarize(vals, n_boot=n_boot, seed=30))
        d["failures"] = float(failures.get(cond, 0))
        out.setdefault(name, {})[cond] = d
    return out


def _score_e2e(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    ori: dict[str, list[float]] = {}
    impact: dict[str, list[float]] = {}
    pos: dict[str, list[float]] = {}
    fallback: dict[str, list[float]] = {}
    fails: dict[str, int] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        packet = ImuPacket(
            frame=case.swing.packet.frame,
            t=case.t,
            gyro=case.gyro,
            accel=case.accel,
        )
        try:
            report = analyze_swing(packet)
        except Exception:
            fails[case.error_label] = fails.get(case.error_label, 0) + 1
            continue
        ph = case.swing.phases_true
        addr = min(ph.address_idx, report.quats.shape[0] - 1)
        n = min(report.quats.shape[0], case.swing.quats_true.shape[0])
        aligned = _yaw_align(report.quats[:n], case.swing.quats_true[:n], addr)
        ori.setdefault(case.error_label, []).append(
            float(np.mean(orientation_error_deg(aligned, case.swing.quats_true[:n])))
        )
        impact.setdefault(case.error_label, []).append(
            abs(report.phases.impact_idx - ph.impact_idx) / fs * 1000.0
        )
        truth = case.swing.positions_true[:n] - case.swing.positions_true[ph.address_idx]
        window = slice(ph.address_idx, min(ph.finish_idx + 1, n))
        pos_e = _yaw_rotate_positions(
            report.positions[:n], report.quats[:n], case.swing.quats_true[:n], addr
        )
        pos.setdefault(case.error_label, []).append(
            float(np.mean(np.linalg.norm(pos_e[window] - truth[window], axis=1) * 100.0))
        )
        fallback.setdefault(case.error_label, []).append(
            float(report.meta.get("fallback", 0.0))
        )
    out: dict[str, Any] = {}
    for cond in sorted(set(ori) | set(impact) | set(pos)):
        out[cond] = {
            "orientation_deg": _sum_dict(summarize(ori.get(cond, []), n_boot=n_boot, seed=50)),
            "impact_ms": _sum_dict(summarize(impact.get(cond, []), n_boot=n_boot, seed=51)),
            "position_cm": _sum_dict(summarize(pos.get(cond, []), n_boot=n_boot, seed=52)),
            "fallback_rate": _sum_dict(summarize(fallback.get(cond, []), n_boot=n_boot, seed=53)),
            "pipeline_failures": fails.get(cond, 0),
        }
    return out


def _score_track(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    if not cases:
        return {"empty": True}
    return {
        "n_cases": len(cases),
        "generator": cases[0].generator,
        "orientation": _score_orientation(cases, n_boot),
        "trajectory": _score_trajectory(cases, n_boot),
        "events": _score_events(cases, n_boot),
        "e2e": _score_e2e(cases, n_boot),
        "credibility": (
            "upper_bound_isomorphic"
            if cases[0].generator == "analytic"
            else (
                "assumption_stress"
                if "violate" in cases[0].generator
                else (
                    "robust_golden_regime"
                    if cases[0].generator
                    in {
                        "pro_regime",
                        "casting_pathology",
                        "fs_stress",
                        "clip_stress",
                        "lefty_mirror",
                    }
                    else "cross_generator_accurate"
                )
            )
        ),
    }


def _run_session_mc(seeds: list[int], n_boot: int) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = {}
    for seed in seeds:
        session = make_session(n_swings=8, rest_between_s=3.0, seed=seed)
        fs = session.packet.frame.fs_hz
        dt = 1.0 / fs
        for lname, factory in (
            ("consumer", ImuErrorParams.consumer_grade),
            ("harsh", ImuErrorParams.harsh),
        ):
            _, gyro, accel, _ = apply_imu_errors(
                session.packet.t, session.packet.gyro, session.packet.accel, factory(seed)
            )
            q0, _, _ = ahrs_init.estimate_address_orientation(gyro, accel, fs)
            bias, _ = ahrs_init.estimate_gyro_bias(gyro, accel, fs)
            runs = []
            for est in ahrs_suite.make_default_suite():
                quats, _ = est.run(gyro, accel, dt, q0=q0)
                runs.append((est.name, quats))
            q_rb, _ = ahrs_suite.GyroOnly().run(gyro - bias, accel, dt, q0=q0)
            runs.append(("gyro_only+restbias", q_rb))
            for name, quats in runs:
                aligned = _yaw_align(quats, session.quats_true, 0)
                err = float(np.mean(orientation_error_deg(aligned, session.quats_true)))
                buckets.setdefault((name, lname), []).append(err)
    out: dict[str, Any] = {}
    for (alg, cond), vals in sorted(buckets.items()):
        out.setdefault(alg, {})[cond] = _sum_dict(summarize(vals, n_boot=n_boot, seed=40))
    return out


def _score_multisense(
    n_boot: int,
    max_swings: int = 30,
    *,
    subjects: list[str] | None = None,
    track_label: str = "external_multisense",
    club_speed_min_m_s: float | None = None,
) -> dict[str, Any]:
    st = msg.dataset_status()
    if not st["ready"]:
        return {
            "status": "unavailable",
            "reason": "documentation or extracted HDF5 swings missing; "
            "run scripts/fetch_multisense.py",
            "dataset": st,
            "track": track_label,
        }
    ori: list[float] = []
    impact: list[float] = []
    pos: list[float] = []
    impact_modes: list[str] = []
    speeds: list[float] = []
    fails = 0
    n = 0
    for case in msg.iter_local_swings(
        max_swings=max_swings,
        subjects=subjects,
        club_speed_min_m_s=club_speed_min_m_s,
    ):
        n += 1
        try:
            report = analyze_swing(case.packet)
        except Exception:
            fails += 1
            continue
        fs = case.packet.frame.fs_hz
        impact.append(abs(report.phases.impact_idx - case.impact_idx) / fs * 1000.0)
        nq = min(report.quats.shape[0], case.quats_ref.shape[0])
        aligned = _yaw_align(report.quats[:nq], case.quats_ref[:nq], 0)
        ori.append(float(np.mean(orientation_error_deg(aligned, case.quats_ref[:nq]))))
        truth = case.positions_ref[:nq] - case.positions_ref[0]
        pos_e = _yaw_rotate_positions(
            report.positions[:nq],
            report.quats[:nq],
            case.quats_ref[:nq],
            0,
        )
        pos.append(float(np.mean(np.linalg.norm(pos_e - truth, axis=1) * 100.0)))
        impact_modes.append(str(report.meta.get("impact_mode", "unknown")))
        sp = float(case.reference.get("club_speed_m_s", float("nan")))
        if np.isfinite(sp):
            speeds.append(sp)

    if n == 0:
        return {
            "status": "unavailable",
            "reason": "no swings loaded for requested subjects/filters",
            "dataset": st,
            "track": track_label,
            "subjects_filter": subjects,
            "club_speed_min_m_s": club_speed_min_m_s,
        }

    return {
        "status": "ok",
        "track": track_label,
        "provenance": "multisense_mocap_derived_imu",
        "doi": msg.DOI,
        "n_swings": n,
        "pipeline_failures": fails,
        "subjects_filter": subjects,
        "club_speed_min_m_s": club_speed_min_m_s,
        "club_speed_m_s": _sum_dict(summarize(speeds, n_boot=n_boot, seed=63))
        if speeds
        else None,
        "dataset": st,
        "orientation_deg": _sum_dict(summarize(ori, n_boot=n_boot, seed=60)),
        "impact_ms": _sum_dict(summarize(impact, n_boot=n_boot, seed=61)),
        "position_cm": _sum_dict(summarize(pos, n_boot=n_boot, seed=62)),
        "events": {"impact": _sum_dict(summarize(impact, n_boot=n_boot, seed=61))},
        "impact_mode_counts": {
            m: int(sum(1 for x in impact_modes if x == m))
            for m in sorted(set(impact_modes))
        },
        "credibility": "external_real_motion_mocap_derived_imu",
        "caveat": (
            "Input IMU is derived from mocap joint kinematics (PN 21-bone), not a "
            "raw wrist MEMS stream. Adapter converts Y-up→Z-up, derives body gyro "
            "from quaternion log (rad/s), and resamples irregular timestamps. "
            "Motion distribution is external; sensor noise is not."
            + (
                " Elite subset is an eval gate only — not an in-product posture library."
                if subjects
                else ""
            )
            + (
                f" Club-speed stratum ≥ {club_speed_min_m_s} m/s."
                if club_speed_min_m_s is not None
                else ""
            )
        ),
    }


def _score_cmu64(n_boot: int, max_swings: int = 8) -> dict[str, Any]:
    st = cmu64.dataset_status()
    if not st["ready"]:
        return {
            "status": "unavailable",
            "reason": "run scripts/fetch_cmu64.py (or place ASF/AMC under data/cmu64/raw)",
            "dataset": st,
            "track": "external_cmu64",
        }
    from golfmate_algo.ahrs.suite import GyroOnly

    ori: list[float] = []
    ori_gyro: list[float] = []
    impact: list[float] = []
    pos: list[float] = []
    fails = 0
    n = 0
    for case in cmu64.iter_local_swings(max_swings=max_swings):
        n += 1
        try:
            report = analyze_swing(case.packet)
        except Exception:
            fails += 1
            continue
        fs = case.packet.frame.fs_hz
        dt = 1.0 / fs
        impact.append(
            abs(report.phases.impact_idx - case.phases.impact_idx) / fs * 1000.0
        )
        nq = min(report.quats.shape[0], case.quats_ref.shape[0])
        aligned = _yaw_align(report.quats[:nq], case.quats_ref[:nq], 0)
        ori.append(float(np.mean(orientation_error_deg(aligned, case.quats_ref[:nq]))))
        # SciRep-style: pure gyro is the fairer ceiling for mocap-synth IMU
        q_g, _ = GyroOnly().run(
            case.packet.gyro, case.packet.accel, dt, q0=case.quats_ref[0]
        )
        aligned_g = _yaw_align(q_g[:nq], case.quats_ref[:nq], 0)
        ori_gyro.append(
            float(np.mean(orientation_error_deg(aligned_g, case.quats_ref[:nq])))
        )
        truth = case.positions_ref[:nq] - case.positions_ref[0]
        pos_e = _yaw_rotate_positions(
            report.positions[:nq], report.quats[:nq], case.quats_ref[:nq], 0
        )
        pos.append(float(np.mean(np.linalg.norm(pos_e - truth, axis=1) * 100.0)))
    if n == 0:
        return {
            "status": "unavailable",
            "reason": "no CMU trials parsed",
            "dataset": st,
            "track": "external_cmu64",
        }
    return {
        "status": "ok",
        "track": "external_cmu64",
        "provenance": "cmu64_mocap_synth_imu",
        "n_swings": n,
        "pipeline_failures": fails,
        "dataset": st,
        "orientation_deg": _sum_dict(summarize(ori, n_boot=n_boot, seed=70)),
        "orientation_gyro_only_deg": _sum_dict(
            summarize(ori_gyro, n_boot=n_boot, seed=73)
        ),
        "impact_ms": _sum_dict(summarize(impact, n_boot=n_boot, seed=71)),
        "position_cm": _sum_dict(summarize(pos, n_boot=n_boot, seed=72)),
        "credibility": "external_real_motion_mocap_synth_imu",
        "caveat": (
            "CMU Subject 64 golf mocap → synth wrist IMU via ASF/AMC FK. "
            "Commercial-friendly license (do not resell mocap). "
            "Impact is kinematic (no ball). Not raw MEMS. "
            "Gate uses gyro-only orientation (SciRep-style) because mocap-diff "
            "accel is too noisy for tilt fusion."
        ),
        "license_note": st.get("license_note"),
    }


# --------------------------------------------------------------------------- report


def _fmt_ci(s: dict[str, Any] | None) -> str:
    if not s or "mean" not in s:
        return "—"
    return f"{s['mean']:.2f} [{s.get('ci95_lo', float('nan')):.2f}, {s.get('ci95_hi', float('nan')):.2f}]"


def render_zero_trust_markdown(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    by = payload["by_track"]
    gates = payload["gates"]
    lines: list[str] = []
    lines.append("# Golf Mate 零信任 Benchmark 报告")
    lines.append("")
    lines.append(
        f"> protocol `{meta.get('protocol_id', PROTOCOL_ID)}` · mode `{meta.get('mode')}` · "
        f"`{meta['generated_at']}` · {meta['elapsed_s']:.1f}s · "
        f"gates **{'PASS' if gates.get('pass') else 'FAIL'}**"
    )
    lines.append("")
    lines.append("## 可信度分层（必读）")
    lines.append("")
    lines.append("| 轨道 | 含义 | 可否对外产品精度引用 |")
    lines.append("|------|------|-------------------|")
    lines.append("| isomorphic_analytic | 与杠杆解同构的解析平面 | **否**（上界） |")
    lines.append("| cross_multibody | 独立多刚体生成器 | **可**（准确仿真） |")
    lines.append("| violation_stress | 故意破坏刚性假设 | 测诚实度，非精度 |")
    lines.append("| external_multisense | MultiSenseGolf 真人运动 | **可**（零信任运动分布） |")
    lines.append("")

    if gates.get("violations"):
        lines.append("### 闸门失败")
        for v in gates["violations"]:
            lines.append(f"- {v}")
        lines.append("")
    if gates.get("notes"):
        lines.append("### 闸门备注")
        for n in gates["notes"]:
            lines.append(f"- {n}")
        lines.append("")

    # Headline from cross_multibody consumer e2e
    cross = by.get("cross_multibody", {})
    e2e = cross.get("e2e", {})
    lines.append("## 1. 准确仿真头条（cross_multibody / E2E）")
    lines.append("")
    lines.append("| 条件 | 姿态 ° | Impact ms | 位置 cm | fallback |")
    lines.append("|------|-------:|----------:|--------:|---------:|")
    for cond in ("ideal", "consumer", "harsh"):
        row = e2e.get(cond)
        if not row:
            continue
        lines.append(
            f"| {cond} | {_fmt_ci(row['orientation_deg'])} | {_fmt_ci(row['impact_ms'])} | "
            f"{_fmt_ci(row['position_cm'])} | {_fmt_ci(row.get('fallback_rate'))} |"
        )
    lines.append("")

    # Orientation leaders on cross track
    ori = cross.get("orientation", {}).get("per_swing", {})
    if ori:
        lines.append("## 2. 姿态对抗（cross_multibody，按挥杆均值 °）")
        lines.append("")
        lines.append("| 算法 | ideal | consumer | harsh |")
        lines.append("|------|------:|---------:|------:|")
        for alg in sorted(ori.keys()):
            cells = [_fmt_ci(ori[alg].get(f"{c}/all")) for c in ("ideal", "consumer", "harsh")]
            lines.append(f"| {alg} | " + " | ".join(cells) + " |")
        lines.append("")

    sess = payload.get("session", {})
    if sess:
        lines.append("## 3. 会话漂移（analytic session，~24 s）")
        lines.append("")
        lines.append("| 算法 | consumer | harsh |")
        lines.append("|------|---------:|------:|")
        for alg in sorted(sess.keys()):
            lines.append(
                f"| {alg} | {_fmt_ci(sess[alg].get('consumer'))} | {_fmt_ci(sess[alg].get('harsh'))} |"
            )
        lines.append("")

    # Events
    ev = cross.get("events", {})
    if ev:
        lines.append("## 4. 事件检测（cross_multibody，ms）")
        lines.append("")
        lines.append("| 事件 | ideal | consumer | harsh |")
        lines.append("|------|------:|---------:|------:|")
        for name in ("address", "top", "impact", "finish"):
            cells = [_fmt_ci(ev.get(name, {}).get(c)) for c in ("ideal", "consumer", "harsh")]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")

    # Trajectory + violation
    traj = cross.get("trajectory", {})
    viol = by.get("violation_stress", {})
    lines.append("## 5. 轨迹与打假")
    lines.append("")
    lines.append("| 方法 / 指标 | ideal | consumer | harsh |")
    lines.append("|-------------|------:|---------:|------:|")
    for alg in sorted(traj.get("position_cm", {}).keys()):
        cells = [
            _fmt_ci(traj["position_cm"][alg].get(c)) for c in ("ideal", "consumer", "harsh")
        ]
        lines.append(f"| {alg} cm | " + " | ".join(cells) + " |")
    for cond in ("ideal", "consumer", "harsh"):
        pass
    lines.append(
        "| residual clean | "
        + " | ".join(
            _fmt_ci(traj.get("lever_arm_residual_m_s2", {}).get(c))
            for c in ("ideal", "consumer", "harsh")
        )
        + " |"
    )
    vtraj = viol.get("trajectory", {})
    lines.append(
        "| residual violate | "
        + " | ".join(
            _fmt_ci(vtraj.get("lever_arm_residual_m_s2", {}).get(c))
            for c in ("ideal", "consumer", "harsh")
        )
        + " |"
    )
    lines.append(
        "| invalid rate violate | "
        + " | ".join(
            _fmt_ci(vtraj.get("lever_arm_invalid", {}).get(c))
            for c in ("ideal", "consumer", "harsh")
        )
        + " |"
    )
    lines.append("")

    # Isomorphic disclaimer
    iso = by.get("isomorphic_analytic", {})
    if iso.get("e2e"):
        lines.append("## 6. 同构上界（不可单独引用为产品精度）")
        lines.append("")
        lines.append("| 条件 | 姿态 ° | Impact ms | 位置 cm |")
        lines.append("|------|-------:|----------:|--------:|")
        for cond, row in iso["e2e"].items():
            lines.append(
                f"| {cond} | {_fmt_ci(row['orientation_deg'])} | "
                f"{_fmt_ci(row['impact_ms'])} | {_fmt_ci(row['position_cm'])} |"
            )
        lines.append("")

    ext = by.get("external_multisense", {})
    lines.append("## 7. 外部零信任（MultiSenseGolf）")
    lines.append("")
    if ext.get("status") != "ok":
        lines.append(f"状态：**unavailable** — {ext.get('reason', 'n/a')}")
    else:
        lines.append(
            f"状态：**ok** · n={ext.get('n_swings')} · doi:`{ext.get('doi')}` · "
            f"{ext.get('caveat', '')}"
        )
        lines.append("")
        lines.append("| 指标 | mean [CI] |")
        lines.append("|------|----------:|")
        lines.append(f"| 姿态 ° | {_fmt_ci(ext.get('orientation_deg'))} |")
        lines.append(f"| Impact ms | {_fmt_ci(ext.get('impact_ms'))} |")
        lines.append(f"| 位置 cm | {_fmt_ci(ext.get('position_cm'))} |")
    lines.append("")

    elite = by.get("external_multisense_elite", {})
    lines.append("## 7b. MultiSenseGolf 高水平子集（评测闸，非产品示范库）")
    lines.append("")
    if elite.get("status") != "ok":
        lines.append(
            f"状态：**{elite.get('status', 'unavailable')}** — {elite.get('reason', 'n/a')}"
        )
        if elite.get("elite_manifest_subjects"):
            lines.append(
                f"Manifest subjects: `{', '.join(elite['elite_manifest_subjects'])}` "
                "(extract these Subject zips to score)."
            )
    else:
        lines.append(
            f"状态：**ok** · n={elite.get('n_swings')} · "
            f"subjects={elite.get('subjects_filter')} · {elite.get('caveat', '')}"
        )
        lines.append("")
        lines.append("| 指标 | mean [CI] |")
        lines.append("|------|----------:|")
        lines.append(f"| 姿态 ° | {_fmt_ci(elite.get('orientation_deg'))} |")
        lines.append(f"| Impact ms | {_fmt_ci(elite.get('impact_ms'))} |")
        lines.append(f"| 位置 cm | {_fmt_ci(elite.get('position_cm'))} |")
    lines.append("")

    hs = by.get("external_multisense_high_speed", {})
    lines.append("## 7c. MultiSense 高球速分层（club_speed ≥ 20 m/s）")
    lines.append("")
    if hs.get("status") != "ok":
        lines.append(f"状态：**{hs.get('status', 'unavailable')}** — {hs.get('reason', 'n/a')}")
    else:
        lines.append(
            f"状态：**ok** · n={hs.get('n_swings')} · {hs.get('caveat', '')}"
        )
        lines.append("")
        lines.append("| 指标 | mean [CI] |")
        lines.append("|------|----------:|")
        lines.append(f"| 姿态 ° | {_fmt_ci(hs.get('orientation_deg'))} |")
        lines.append(f"| Impact ms | {_fmt_ci(hs.get('impact_ms'))} |")
        lines.append(f"| 位置 cm | {_fmt_ci(hs.get('position_cm'))} |")
        lines.append(f"| Club speed m/s | {_fmt_ci(hs.get('club_speed_m_s'))} |")
    lines.append("")

    cmu = by.get("external_cmu64", {})
    lines.append("## 7d. CMU Subject 64（商用友好 mocap → synth IMU）")
    lines.append("")
    if cmu.get("status") != "ok":
        lines.append(f"状态：**{cmu.get('status', 'unavailable')}** — {cmu.get('reason', 'n/a')}")
    else:
        lines.append(
            f"状态：**ok** · n={cmu.get('n_swings')} · {cmu.get('caveat', '')}"
        )
        lines.append("")
        lines.append("| 指标 | mean [CI] |")
        lines.append("|------|----------:|")
        lines.append(f"| 姿态 ° | {_fmt_ci(cmu.get('orientation_deg'))} |")
        lines.append(f"| Impact ms | {_fmt_ci(cmu.get('impact_ms'))} |")
        lines.append(f"| 位置 cm | {_fmt_ci(cmu.get('position_cm'))} |")
    lines.append("")

    lines.append("## 7e. Robust golden synth tracks")
    lines.append("")
    lines.append("| Track | ori ° | impact ms | pos cm |")
    lines.append("|-------|------:|----------:|-------:|")
    for name in (
        "pro_regime",
        "casting_pathology",
        "fs_stress",
        "clip_stress",
        "lefty_mirror",
    ):
        tr = by.get(name, {})
        e2e = tr.get("e2e", {}) if isinstance(tr, dict) else {}
        row = e2e.get("consumer") or next(iter(e2e.values()), None) if e2e else None
        if not row:
            lines.append(f"| {name} | — | — | — |")
        else:
            lines.append(
                f"| {name} | {_fmt_ci(row.get('orientation_deg'))} | "
                f"{_fmt_ci(row.get('impact_ms'))} | {_fmt_ci(row.get('position_cm'))} |"
            )
    lines.append("")

    wit = by.get("external_wit_kinnet", {})
    lines.append("## 7f. WIT-KinNet stub（最高产品契合，待发布）")
    lines.append("")
    lines.append(
        f"状态：**{wit.get('status', 'unavailable')}** — {wit.get('reason', 'n/a')} · "
        f"{wit.get('arxiv', '')}"
    )
    lines.append("")

    deg = payload.get("degradation", {})
    if deg.get("session"):
        lines.append("## 8. 退化曲线（会话，gated vs gyro_only）")
        lines.append("")
        lines.append("| scale | gated ° | gyro_only ° |")
        lines.append("|------:|--------:|------------:|")
        for row in deg["session"]:
            lines.append(
                f"| {row['scale']:.1f} | {row['gated_mean']:.2f} | {row['gyro_only_mean']:.2f} |"
            )
        lines.append("")

    lines.append("## 9. 复现")
    lines.append("")
    lines.append("```bash")
    lines.append("cd golf-mate/algo && source .venv/bin/activate")
    lines.append("python scripts/fetch_multisense.py --max-swings 30")
    lines.append("python scripts/fetch_cmu64.py")
    lines.append("python scripts/seal_holdout.py")
    lines.append("python -m golfmate_algo.bench.evaluate --mode full")
    lines.append("pytest -q")
    lines.append("```")
    lines.append("")
    lines.append("Golden catalog: `docs/research/07_golden_sources.md`.")
    lines.append("")
    return "\n".join(lines)


def _json_ready(obj: Any) -> Any:
    if isinstance(obj, Summary):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): _json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_ready(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    return obj


def run_evaluation(
    *,
    mode: Mode = "dev",
    n_boot: int = 2000,
    quick: bool = False,
    generators: list[str] | None = None,
    include_multisense: bool = True,
    include_degradation: bool = True,
    n_dev: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if quick:
        mode = "dev"
        n_boot = min(n_boot, 400)
        n_dev = n_dev or 2
        include_degradation = False
    gens = generators or ["analytic", "multibody", "multibody_violate", "robust_golden"]
    tracks = build_protocol_cases(mode=mode if mode != "full" else "dev", generators=gens, n_dev=n_dev)
    # full mode also scores holdout seeds separately for seal check
    holdout_info: dict[str, Any] = {"enabled": False}
    if mode in ("holdout", "full"):
        try:
            sealed = load_holdout_manifest()
        except FileNotFoundError:
            seal_holdout()
            sealed = load_holdout_manifest()
        hold_tracks = build_protocol_cases(
            mode="holdout",
            generators=[
                g
                for g in gens
                if g not in ("multibody_violate", "robust_golden")
            ],
        )
        mismatches = verify_holdout_inputs(hold_tracks)
        holdout_info = {
            "enabled": True,
            "artifact_sha256": sealed.get("artifact_sha256"),
            "mismatches": mismatches,
            "n_cases": {k: len(v) for k, v in hold_tracks.items()},
        }
        if mode == "holdout":
            tracks = hold_tracks

    by_track: dict[str, Any] = {}
    for name, cases in tracks.items():
        # quick: consumer-only to save time
        if quick:
            cases = [
                c
                for c in cases
                if c.error_label == "consumer" or c.error_label.startswith("consumer")
            ]
        by_track[name] = _score_track(cases, n_boot)

    if include_multisense:
        by_track["external_multisense"] = _score_multisense(
            n_boot, max_swings=10 if quick else 30
        )
        # High club-speed stratum (even on non-elite subjects) — faster timing
        by_track["external_multisense_high_speed"] = _score_multisense(
            n_boot,
            max_swings=10 if quick else 20,
            club_speed_min_m_s=20.0,
            track_label="external_multisense_high_speed",
        )
        from golfmate_algo.reference.elite import elite_subject_ids

        elite_ids = elite_subject_ids()
        # Only request subjects that are actually extracted locally.
        available = set(st for st in msg.dataset_status().get("subjects_extracted", []))
        elite_local = [s for s in elite_ids if s in available]
        if elite_local:
            by_track["external_multisense_elite"] = _score_multisense(
                n_boot,
                max_swings=10 if quick else 30,
                subjects=elite_local,
                track_label="external_multisense_elite",
            )
            by_track["external_multisense_elite"]["elite_manifest_subjects"] = elite_ids
        else:
            by_track["external_multisense_elite"] = {
                "status": "unavailable",
                "reason": (
                    "elite subjects not extracted locally; manifest lists "
                    f"{elite_ids or 'none'}"
                ),
                "elite_manifest_subjects": elite_ids,
                "track": "external_multisense_elite",
            }
        by_track["external_cmu64"] = _score_cmu64(n_boot, max_swings=5 if quick else 10)
        by_track["external_wit_kinnet"] = {
            "status": "unavailable",
            **wit_kinnet.dataset_status(),
            "track": "external_wit_kinnet",
        }
    else:
        by_track["external_multisense"] = {
            "status": "skipped",
            "reason": "include_multisense=False",
        }
        by_track["external_multisense_elite"] = {
            "status": "skipped",
            "reason": "include_multisense=False",
        }

    session_seeds = list(range(n_dev or 8))[: (2 if quick else 8)]
    session = _run_session_mc(session_seeds, n_boot)
    degradation = (
        benchmark_degradation(
            seeds=session_seeds[:5],
            n_boot=min(n_boot, 800),
            scales=[0.0, 1.0, 2.0] if quick else None,
        )
        if include_degradation
        else {}
    )

    elapsed = time.perf_counter() - t0
    pmeta = protocol_meta(
        mode,
        gens,
        sealed=holdout_info.get("enabled", False),
        artifact_sha256=holdout_info.get("artifact_sha256"),
    )
    payload: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": elapsed,
            "mode": mode,
            "protocol_id": pmeta.protocol_id,
            "generators": list(gens),
            "n_boot": n_boot,
            "quick": quick,
            "disclaimer_isomorphic_upper_bound": True,
            "fs_hz": 200.0,
            "scirep_position_cm_ref": scirep_budgets.POSITION_CM_WHOLE_SWING,
            "golden_sources": [
                {"rank": s.rank, "name": s.name, "commercial_eval_ok": s.commercial_eval_ok}
                for s in ranked_catalog()
            ],
        },
        "by_track": by_track,
        "session": session,
        "degradation": degradation,
        "holdout": holdout_info,
        "gates": {},
    }
    payload["gates"] = check_gates(payload)
    return _json_ready(payload)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Golf Mate zero-trust benchmark")
    p.add_argument("--mode", choices=["dev", "holdout", "full"], default="full")
    p.add_argument("--boot", type=int, default=2000)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--out", type=str, default="")
    p.add_argument("--no-multisense", action="store_true")
    args = p.parse_args(argv)

    payload = run_evaluation(
        mode=args.mode,  # type: ignore[arg-type]
        n_boot=args.boot,
        quick=args.quick,
        include_multisense=not args.no_multisense,
    )
    md = render_zero_trust_markdown(payload)

    algo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out) if args.out else algo_root / "bench_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "benchmark_zero_trust.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (out_dir / "BENCHMARK_ZERO_TRUST.md").write_text(md, encoding="utf-8")

    docs = algo_root.parent / "docs" / "research"
    if docs.is_dir():
        (docs / "06_zero_trust_benchmark.md").write_text(md, encoding="utf-8")
        (docs / "benchmark_zero_trust.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    art = Path("/opt/cursor/artifacts")
    if art.is_dir():
        (art / "BENCHMARK_ZERO_TRUST.md").write_text(md, encoding="utf-8")
        (art / "benchmark_zero_trust.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    print(md)
    print(f"\nWrote {out_dir / 'BENCHMARK_ZERO_TRUST.md'}")
    print(f"gates.pass = {payload['gates']['pass']}")
    return 0 if payload["gates"]["pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
