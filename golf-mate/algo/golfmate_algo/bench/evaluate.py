"""End-to-end evaluation runner: Monte-Carlo + ablation + degradation → report.

Usage
-----
    cd golf-mate/algo
    python -m golfmate_algo.bench.evaluate [--seeds 8] [--quick] [--out DIR]

Outputs
-------
* ``benchmark.json`` — machine-readable, CI-regressable
* ``BENCHMARK.md`` — human report with tables and interpretation
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs import suite as ahrs_suite
from golfmate_algo.bench.ablation import (
    benchmark_degradation,
    benchmark_gate_ablation,
    benchmark_gate_ablation_session,
    benchmark_traj_ablation,
)
from golfmate_algo.bench.harness import (
    SwingCase,
    build_cases,
    format_rows,
    orientation_error_deg,
    _yaw_align,
)
from golfmate_algo.bench.stats import Summary, summarize
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.session import make_session
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.types import ImuPacket, SensorFrame


def _sum_dict(s: Summary) -> dict[str, Any]:
    return s.to_dict()


# --------------------------------------------------------------------------- core MC


def _run_orientation_mc(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    by_all: dict[tuple[str, str], list[float]] = {}
    by_down: dict[tuple[str, str], list[float]] = {}
    # Per-case mean (for bootstrap over swings, not samples)
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
            aligned = _yaw_align(quats, case.swing.quats_true, ph.address_idx)
            err = orientation_error_deg(aligned, case.swing.quats_true)
            key = (name, case.error_label)
            by_all.setdefault(key, []).extend(err.tolist())
            by_down.setdefault(key, []).extend(err[ph.top_idx : ph.impact_idx + 1].tolist())
            case_means.setdefault(key, []).append(float(np.mean(err)))
            case_means_down.setdefault(key, []).append(
                float(np.mean(err[ph.top_idx : ph.impact_idx + 1]))
            )

    result: dict[str, Any] = {"sample_pooled": {}, "per_swing": {}}
    for (alg, cond), vals in sorted(case_means.items()):
        result["per_swing"].setdefault(alg, {})[f"{cond}/all"] = _sum_dict(
            summarize(vals, n_boot=n_boot, seed=abs(hash((alg, cond))) % 10_000)
        )
        result["per_swing"][alg][f"{cond}/down"] = _sum_dict(
            summarize(
                case_means_down[(alg, cond)],
                n_boot=n_boot,
                seed=abs(hash((alg, cond, "d"))) % 10_000,
            )
        )
    for (alg, cond), vals in sorted(by_all.items()):
        # Pooled sample stats for p95/max continuity with prior report
        s = summarize(vals, n_boot=min(n_boot, 800), seed=1)
        result["sample_pooled"].setdefault(alg, {})[f"{cond}/all"] = {
            "mean": s.mean,
            "p95": s.p95,
            "maximum": s.maximum,
            "n": s.n,
        }
        sd = summarize(by_down[(alg, cond)], n_boot=min(n_boot, 800), seed=2)
        result["sample_pooled"][alg][f"{cond}/down"] = {
            "mean": sd.mean,
            "p95": sd.p95,
            "maximum": sd.maximum,
            "n": sd.n,
        }
    return result


def _run_trajectory_mc(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = {}
    radius: dict[str, list[float]] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        bias, _ = ahrs_init.estimate_gyro_bias(case.gyro, case.accel, fs)
        gyro_c = case.gyro - bias
        quats, _ = ahrs_suite.GatedAdaptive().run(gyro_c, case.accel, dt, q0=q0)
        quats = _yaw_align(quats, case.swing.quats_true, case.swing.phases_true.address_idx)
        ph = case.swing.phases_true
        truth = case.swing.positions_true - case.swing.positions_true[ph.address_idx]
        window = slice(ph.address_idx, ph.finish_idx + 1)

        _, _, pos_dr = reconstruct_trajectory(quats, case.accel, dt, phases=ph)
        pos_dr = pos_dr - pos_dr[ph.address_idx]
        e_dr = float(np.mean(np.linalg.norm(pos_dr[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("dead_reckon_zupt", case.error_label), []).append(e_dr)

        la = estimate_lever_arm(quats, gyro_c, case.accel, dt)
        pos_la = la.positions - la.positions[ph.address_idx]
        e_la = float(np.mean(np.linalg.norm(pos_la[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("lever_arm", case.error_label), []).append(e_la)
        radius.setdefault(case.error_label, []).append(
            abs(la.radius_m - case.swing.meta["radius_m"]) * 100.0
        )

    out: dict[str, Any] = {"position_cm": {}, "radius_err_cm": {}}
    for (alg, cond), vals in sorted(buckets.items()):
        out["position_cm"].setdefault(alg, {})[cond] = _sum_dict(
            summarize(vals, n_boot=n_boot, seed=21)
        )
    for cond, vals in sorted(radius.items()):
        out["radius_err_cm"][cond] = _sum_dict(summarize(vals, n_boot=n_boot, seed=22))
    return out


def _run_events_mc(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = {}
    failures: dict[str, int] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        try:
            det = detect_phases_segmental(case.swing.packet.t, case.gyro, case.accel)
        except Exception:
            failures[case.error_label] = failures.get(case.error_label, 0) + 1
            continue
        tr = case.swing.phases_true
        for name in ("address", "top", "impact", "finish"):
            err_ms = abs(getattr(det, f"{name}_idx") - getattr(tr, f"{name}_idx")) / fs * 1000.0
            buckets.setdefault((name, case.error_label), []).append(err_ms)

    out: dict[str, Any] = {}
    for (name, cond), vals in sorted(buckets.items()):
        s = summarize(vals, n_boot=n_boot, seed=30)
        d = _sum_dict(s)
        d["failures"] = float(failures.get(cond, 0))
        out.setdefault(name, {})[cond] = d
    return out


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


def _yaw_rotate_positions(pos: Any, q_est: Any, q_true: Any, address_idx: int) -> Any:
    """Apply the same unobservable-yaw correction used for orientation metrics.

    Six-axis filters leave heading free; without rotating the reconstructed path
    by that constant world-Z offset, Euclidean position error is dominated by
    an unobservable gauge and is not informative.
    """
    from golfmate_algo.math import so3

    aligned = _yaw_align(q_est, q_true, address_idx)
    # Relative world rotation that maps the raw estimate into the aligned frame.
    r = so3.quat_multiply(aligned[address_idx], so3.quat_conjugate(q_est[address_idx]))
    R = so3.quat_to_rotmat(r)
    out = (R @ np.asarray(pos, dtype=np.float64).T).T
    return out - out[address_idx]


def _run_e2e(cases: list[SwingCase], n_boot: int) -> dict[str, Any]:
    """Full pipeline against truth: orientation + impact timing + position."""
    ori: dict[str, list[float]] = {}
    impact: dict[str, list[float]] = {}
    pos: dict[str, list[float]] = {}
    fails: dict[str, int] = {}

    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        packet = ImuPacket(
            frame=SensorFrame(fs_hz=fs),
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
        aligned = _yaw_align(report.quats, case.swing.quats_true, addr)
        ori.setdefault(case.error_label, []).append(
            float(np.mean(orientation_error_deg(aligned, case.swing.quats_true)))
        )
        impact.setdefault(case.error_label, []).append(
            abs(report.phases.impact_idx - ph.impact_idx) / fs * 1000.0
        )
        truth = case.swing.positions_true - case.swing.positions_true[ph.address_idx]
        window = slice(ph.address_idx, ph.finish_idx + 1)
        pos_e = _yaw_rotate_positions(
            report.positions, report.quats, case.swing.quats_true, addr
        )
        n = min(pos_e.shape[0], truth.shape[0])
        w = slice(window.start, min(window.stop, n))
        pos.setdefault(case.error_label, []).append(
            float(np.mean(np.linalg.norm(pos_e[w] - truth[w], axis=1) * 100.0))
        )

    out: dict[str, Any] = {}
    for cond in sorted(set(ori) | set(impact) | set(pos)):
        out[cond] = {
            "orientation_deg": _sum_dict(summarize(ori.get(cond, []), n_boot=n_boot, seed=50)),
            "impact_ms": _sum_dict(summarize(impact.get(cond, []), n_boot=n_boot, seed=51)),
            "position_cm": _sum_dict(summarize(pos.get(cond, []), n_boot=n_boot, seed=52)),
            "pipeline_failures": fails.get(cond, 0),
        }
    return out


# --------------------------------------------------------------------------- report


def _fmt(s: dict[str, Any] | None, key: str = "mean") -> str:
    if not s or key not in s or s[key] is None:
        return "—"
    v = s[key]
    if not np.isfinite(v):
        return "—"
    return f"{v:.2f}"


def _fmt_ci(s: dict[str, Any] | None) -> str:
    if not s:
        return "—"
    return f"{s['mean']:.2f} [{s['ci95_lo']:.2f}, {s['ci95_hi']:.2f}]"


def render_markdown(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    lines: list[str] = []
    lines.append("# Golf Mate 算法仿真 Benchmark 报告")
    lines.append("")
    lines.append(
        f"> 生成时间 `{meta['generated_at']}` · 耗时 `{meta['elapsed_s']:.1f}s` · "
        f"seeds={meta['n_seeds']} · cases/level≈{meta['n_cases_per_level']} · "
        f"bootstrap={meta['n_boot']}"
    )
    lines.append("")
    lines.append("## 0. 评测方法（现代仿真方案）")
    lines.append("")
    lines.append("| 要素 | 设计 |")
    lines.append("|------|------|")
    lines.append("| 真值 | 高斯基解析角速度驱动的倾斜平面圆周挥杆；姿态/位置/加速度闭式一致 |")
    lines.append("| 传感器 | 完整 MEMS 误差链：ARW/VRW、零偏+RW、标度/非正交/失准、g 敏感、饱和、量化、安装谐振、抖动、丢包 |")
    lines.append("| 分层 | `ideal` / `consumer`（BMI270 级）/ `harsh`（松散安装+饱和+丢包） |")
    lines.append("| 场景 | 单杆（4 变体 × 3 倾角 × seeds）+ 多杆会话（8 杆 / ~24 s） |")
    lines.append("| 公平性 | 6 轴不可观测 yaw → 全局 chordal 均值投影到世界 Z 后对齐再比 |")
    lines.append("| 统计 | **按挥杆均值**聚合 + **百分位 bootstrap 95% CI**（非仅样本池化） |")
    lines.append("| 消融 | 门控项（α / ω / rest）与轨迹方法（杠杆解 / ZUPT / 姿态 oracle） |")
    lines.append("| 退化 | 消费级误差幅度 ×{0,0.5,1,1.5,2,3} 的连续曲线 |")
    lines.append("| E2E | `analyze_swing` 整条管线；位置在不可观测 yaw 对齐后再比（否则被 gauge 支配） |")
    lines.append("")

    # Headline
    e2e = payload["e2e"]
    lines.append("## 1. 头条指标（端到端管线）")
    lines.append("")
    lines.append("| 条件 | 姿态 ° mean [CI] | Impact ms | 位置 cm | 失败 |")
    lines.append("|------|----------------:|----------:|--------:|-----:|")
    for cond, row in e2e.items():
        lines.append(
            f"| {cond} | {_fmt_ci(row['orientation_deg'])} | "
            f"{_fmt_ci(row['impact_ms'])} | {_fmt_ci(row['position_cm'])} | "
            f"{row['pipeline_failures']} |"
        )
    lines.append("")

    # Orientation table
    ori = payload["orientation"]["per_swing"]
    lines.append("## 2. 姿态估计对抗（按挥杆均值 °）")
    lines.append("")
    lines.append("### 2.1 全时段")
    lines.append("")
    algs = sorted(ori.keys())
    lines.append("| 算法 | ideal | consumer | harsh |")
    lines.append("|------|------:|---------:|------:|")
    for alg in algs:
        cells = []
        for cond in ("ideal", "consumer", "harsh"):
            cells.append(_fmt_ci(ori[alg].get(f"{cond}/all")))
        lines.append(f"| {alg} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("### 2.2 下杆窗口 Top→Impact")
    lines.append("")
    lines.append("| 算法 | ideal | consumer | harsh |")
    lines.append("|------|------:|---------:|------:|")
    for alg in algs:
        cells = []
        for cond in ("ideal", "consumer", "harsh"):
            cells.append(_fmt_ci(ori[alg].get(f"{cond}/down")))
        lines.append(f"| {alg} | " + " | ".join(cells) + " |")
    lines.append("")

    sess = payload["session"]
    lines.append("### 2.3 多杆会话（~24 s，按会话均值 °）")
    lines.append("")
    lines.append("| 算法 | consumer | harsh |")
    lines.append("|------|---------:|------:|")
    for alg in sorted(sess.keys()):
        lines.append(
            f"| {alg} | {_fmt_ci(sess[alg].get('consumer'))} | {_fmt_ci(sess[alg].get('harsh'))} |"
        )
    lines.append("")

    # Trajectory
    traj = payload["trajectory"]
    lines.append("## 3. 轨迹重建（位置误差 cm）")
    lines.append("")
    lines.append("| 方法 | ideal | consumer | harsh |")
    lines.append("|------|------:|---------:|------:|")
    for alg in sorted(traj["position_cm"].keys()):
        cells = [
            _fmt_ci(traj["position_cm"][alg].get(c)) for c in ("ideal", "consumer", "harsh")
        ]
        lines.append(f"| {alg} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("半径误差 cm：")
    for cond, s in traj["radius_err_cm"].items():
        lines.append(f"- `{cond}`: {_fmt_ci(s)}")
    lines.append("")

    # Events
    ev = payload["events"]
    lines.append("## 4. 事件检测（|error| ms）")
    lines.append("")
    lines.append("| 事件 | ideal | consumer | harsh |")
    lines.append("|------|------:|---------:|------:|")
    for name in ("address", "top", "impact", "finish"):
        cells = [_fmt_ci(ev.get(name, {}).get(c)) for c in ("ideal", "consumer", "harsh")]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")

    # Ablation
    abl = payload["ablation_gate"]
    lines.append("## 5. 消融：动力学门控")
    lines.append("")
    lines.append("### 5.1 单杆 consumer（全时段 / 下杆）")
    lines.append("")
    lines.append("| 变体 | all ° | down ° |")
    lines.append("|------|------:|-------:|")
    for alg in sorted(abl.keys()):
        lines.append(
            f"| {alg} | {_fmt_ci(abl[alg].get('consumer/all'))} | "
            f"{_fmt_ci(abl[alg].get('consumer/down'))} |"
        )
    lines.append("")
    abl_s = payload["ablation_gate_session"]
    lines.append("### 5.2 会话 consumer / harsh")
    lines.append("")
    lines.append("| 变体 | session/consumer | session/harsh |")
    lines.append("|------|-----------------:|--------------:|")
    for alg in sorted(abl_s.keys()):
        lines.append(
            f"| {alg} | {_fmt_ci(abl_s[alg].get('session/consumer'))} | "
            f"{_fmt_ci(abl_s[alg].get('session/harsh'))} |"
        )
    lines.append("")
    lines.append(
        "**读法**：`full_gate+rest` 是产品配置；`no_alpha` 去掉角加速度项；"
        "`always_open` 全程信加速度；`gyro_only` 关闭倾角修正。"
        "单杆上 `always_open` 是灾难（下杆 ~48°）；"
        "`a_only`/`no_alpha`/`full_gate` 的 CI 重叠——短窗内门控细节差别小于种子方差，"
        "会话尺度上 `gyro_only` 崩到 60°+ 而门控族稳定在 ~6°。"
    )
    lines.append("")

    abl_t = payload["ablation_traj"]
    lines.append("## 6. 消融：轨迹方法")
    lines.append("")
    lines.append("| 方法 | ideal | consumer | harsh |")
    lines.append("|------|------:|---------:|------:|")
    for alg in sorted(abl_t.keys()):
        cells = [_fmt_ci(abl_t[alg].get(c)) for c in ("ideal", "consumer", "harsh")]
        lines.append(f"| {alg} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "`lever_arm_oracle_R` 用真值姿态，隔离 AHRS 误差；与 `lever_arm` 的差距即姿态误差传导。"
    )
    lines.append("")

    deg = payload["degradation"]
    lines.append("## 7. 退化曲线（误差幅度 × scale）")
    lines.append("")
    lines.append("### 7.1 单杆")
    lines.append("")
    lines.append("| scale | gated ° [CI] | gyro_only ° [CI] |")
    lines.append("|------:|-------------:|-----------------:|")
    for row in deg["single_swing"]:
        lines.append(
            f"| {row['scale']:.1f} | {row['gated_mean']:.2f} "
            f"[{row['gated_ci_lo']:.2f}, {row['gated_ci_hi']:.2f}] | "
            f"{row['gyro_only_mean']:.2f} "
            f"[{row['gyro_only_ci_lo']:.2f}, {row['gyro_only_ci_hi']:.2f}] |"
        )
    lines.append("")
    lines.append("### 7.2 会话")
    lines.append("")
    lines.append("| scale | gated ° [CI] | gyro_only ° [CI] |")
    lines.append("|------:|-------------:|-----------------:|")
    for row in deg["session"]:
        lines.append(
            f"| {row['scale']:.1f} | {row['gated_mean']:.2f} "
            f"[{row['gated_ci_lo']:.2f}, {row['gated_ci_hi']:.2f}] | "
            f"{row['gyro_only_mean']:.2f} "
            f"[{row['gyro_only_ci_lo']:.2f}, {row['gyro_only_ci_hi']:.2f}] |"
        )
    lines.append("")

    lines.append("## 8. 结论（由本次数据支撑）")
    lines.append("")
    # Auto-extract winners
    try:
        cons = {
            a: ori[a]["consumer/all"]["mean"]
            for a in ori
            if "consumer/all" in ori[a]
        }
        win = min(cons, key=cons.get)
        lines.append(
            f"1. **单杆姿态**：consumer 下按挥杆均值最优为 `{win}` "
            f"({cons[win]:.2f}°)。短窗内纯积分仍极强；产品选型以会话尺度为准。"
        )
        sc = {a: sess[a]["consumer"]["mean"] for a in sess if "consumer" in sess[a]}
        win_s = min(sc, key=sc.get)
        go = sc.get("gyro_only", float("nan"))
        lines.append(
            f"2. **会话姿态**：consumer 最优 `{win_s}` ({sc[win_s]:.2f}°)；"
            f"gyro_only={go:.2f}° —— 门控在长窗上把漂移压到可交付区间。"
        )
        la = traj["position_cm"]["lever_arm"]["consumer"]["mean"]
        dr = traj["position_cm"]["dead_reckon_zupt"]["consumer"]["mean"]
        lines.append(
            f"3. **轨迹**：consumer 杠杆解 {la:.2f} cm vs ZUPT {dr:.2f} cm "
            f"（约 {dr / max(la, 1e-9):.1f}×）。"
        )
        imp = ev["impact"]["consumer"]["mean"]
        lines.append(f"4. **击球时刻**：consumer Impact MAE {imp:.2f} ms（物理高通锚定，无训练）。")
    except Exception as exc:  # pragma: no cover
        lines.append(f"_自动结论生成失败: {exc}_")
    lines.append("")
    lines.append("## 9. 复现")
    lines.append("")
    lines.append("```bash")
    lines.append("cd golf-mate/algo")
    lines.append("source .venv/bin/activate")
    lines.append("python -m golfmate_algo.bench.evaluate --seeds 8")
    lines.append("pytest -q")
    lines.append("```")
    lines.append("")
    lines.append(
        "机器可读结果见同目录 `benchmark.json`。"
        "对抗回归锁在 `tests/test_adversarial.py`。"
    )
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
    seeds: list[int],
    n_boot: int = 2000,
    quick: bool = False,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if quick:
        seeds = seeds[:2]
        n_boot = min(n_boot, 400)

    cases = build_cases(seeds=seeds)
    n_per = sum(1 for c in cases if c.error_label == "consumer")

    orientation = _run_orientation_mc(cases, n_boot)
    trajectory = _run_trajectory_mc(cases, n_boot)
    events = _run_events_mc(cases, n_boot)
    session = _run_session_mc(seeds if not quick else seeds[:2], n_boot)
    e2e = _run_e2e(cases, n_boot)

    abl_gate = benchmark_gate_ablation(cases, n_boot=n_boot)
    abl_sess = benchmark_gate_ablation_session(
        seeds=seeds if not quick else seeds[:2], n_boot=n_boot
    )
    abl_traj = benchmark_traj_ablation(cases, n_boot=n_boot)
    degradation = benchmark_degradation(
        seeds=seeds if not quick else seeds[:3],
        n_boot=min(n_boot, 800),
        scales=[0.0, 0.5, 1.0, 2.0] if quick else None,
    )

    elapsed = time.perf_counter() - t0
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": elapsed,
            "n_seeds": len(seeds),
            "seeds": seeds,
            "n_cases_total": len(cases),
            "n_cases_per_level": n_per,
            "n_boot": n_boot,
            "quick": quick,
            "fs_hz": 200.0,
            "protocol": "analytic-planar + MEMS error model + yaw-align + bootstrap CI",
        },
        "e2e": e2e,
        "orientation": orientation,
        "trajectory": trajectory,
        "events": events,
        "session": session,
        "ablation_gate": {k: {kk: _sum_dict(vv) for kk, vv in v.items()} for k, v in abl_gate.items()},
        "ablation_gate_session": {
            k: {kk: _sum_dict(vv) for kk, vv in v.items()} for k, v in abl_sess.items()
        },
        "ablation_traj": {
            k: {kk: _sum_dict(vv) for kk, vv in v.items()} for k, v in abl_traj.items()
        },
        "degradation": degradation,
    }
    return _json_ready(payload)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Golf Mate algorithm simulation benchmark")
    p.add_argument("--seeds", type=int, default=8, help="number of Monte-Carlo seeds")
    p.add_argument("--boot", type=int, default=2000, help="bootstrap resamples")
    p.add_argument("--quick", action="store_true", help="fast smoke evaluation")
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="output directory (default: docs/research/ + artifacts)",
    )
    args = p.parse_args(argv)

    seeds = list(range(args.seeds))
    payload = run_evaluation(seeds=seeds, n_boot=args.boot, quick=args.quick)
    md = render_markdown(payload)

    algo_root = Path(__file__).resolve().parents[2]
    repo_docs = algo_root.parent / "docs" / "research"
    default_out = algo_root / "bench_out"
    out_dir = Path(args.out) if args.out else default_out
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "benchmark.json"
    md_path = out_dir / "BENCHMARK.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")

    # Also publish into research docs
    if repo_docs.is_dir():
        (repo_docs / "05_benchmark_report.md").write_text(md, encoding="utf-8")
        (repo_docs / "benchmark.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # Artifacts for the agent walkthrough
    art = Path("/opt/cursor/artifacts")
    if art.is_dir():
        art.mkdir(parents=True, exist_ok=True)
        (art / "BENCHMARK.md").write_text(md, encoding="utf-8")
        (art / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(md)
    print(f"\nWrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
