"""Monte-Carlo benchmark harness.

Grades every orientation filter and every trajectory reconstructor against
closed-form truth across a sweep of sensor error levels and swing parameters.
The output is a table of error statistics, which is what makes an algorithm
choice defensible rather than a matter of taste.

Metrics
-------
* orientation: geodesic angle error in degrees (mean / p95 / max), reported both
  over the whole record and over the downswing window where dynamics peak
* trajectory: Euclidean position error in cm against the true wrist path
* events: |detected - true| in milliseconds per phase
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs import suite as ahrs_suite
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.math import so3
from golfmate_algo.synth.analytic import SyntheticSwing, planar_circular_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.multibody import SwingConfig, SwingTruth, build_swing, casting_swing
from golfmate_algo.synth.violations import ViolationSpec, apply_violations, mild_violation
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm

ArrayF = NDArray[np.float64]


@dataclass
class SwingCase:
    label: str
    swing: SyntheticSwing
    gyro: ArrayF
    accel: ArrayF
    t: ArrayF
    error_label: str
    generator: str = "analytic"
    assumptions: dict[str, float | bool | str] = field(
        default_factory=lambda: {"rigid_fixed_center": True}
    )


@dataclass
class MetricRow:
    algorithm: str
    condition: str
    metric: str
    mean: float
    p95: float
    maximum: float
    n: int
    extra: dict[str, float] = field(default_factory=dict)


def _stats(values: Iterable[float]) -> tuple[float, float, float, int]:
    arr = np.asarray(list(values), dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    return (
        float(np.mean(arr)),
        float(np.percentile(arr, 95)),
        float(np.max(arr)),
        int(arr.size),
    )


def orientation_error_deg(q_est: ArrayF, q_true: ArrayF) -> ArrayF:
    n = min(q_est.shape[0], q_true.shape[0])
    return np.array(
        [np.degrees(so3.geodesic_distance(q_est[i], q_true[i])) for i in range(n)],
        dtype=np.float64,
    )


def _yaw_align(q_est: ArrayF, q_true: ArrayF, idx: int = 0) -> ArrayF:
    """Remove the unobservable constant heading offset, fitted over the record.

    Six-axis filters cannot observe yaw, so charging them for heading would
    measure something no 6-axis method can fix. Fitting the offset at a single
    sample is also unfair: a filter still converging at that sample is penalised
    for its whole trace. The offset is therefore the chordal mean of the
    per-sample relative rotations, projected onto rotations about world Z, which
    is exactly the unobservable subgroup.
    """
    del idx
    n = q_est.shape[0]
    rel = np.zeros((n, 4), dtype=np.float64)
    for i in range(n):
        r = so3.quat_multiply(q_true[i], so3.quat_conjugate(q_est[i]))
        rel[i] = r if np.dot(r, rel[0] if i else r) >= 0 else -r
    mean_q = so3.normalize_quat(rel.mean(axis=0))
    R = so3.quat_to_rotmat(mean_q)
    yaw = float(np.arctan2(R[1, 0], R[0, 0]))
    q_off = so3.quat_from_axis_angle([0.0, 0.0, 1.0], yaw)

    out = np.zeros_like(q_est)
    for i in range(n):
        out[i] = so3.normalize_quat(so3.quat_multiply(q_off, q_est[i]))
    return out


def build_cases(
    *,
    seeds: Iterable[int] = (0, 1, 2),
    error_levels: dict[str, Callable[[int], ImuErrorParams]] | None = None,
    fs_hz: float = 200.0,
) -> list[SwingCase]:
    """Cross swing variants with sensor error levels."""
    if error_levels is None:
        error_levels = {
            "ideal": lambda s: ImuErrorParams.ideal(),
            "consumer": lambda s: ImuErrorParams.consumer_grade(seed=s),
            "harsh": lambda s: ImuErrorParams.harsh(seed=s),
        }

    variants = [
        ("normal", dict(casting=False, backswing_s=0.75, downswing_s=0.25)),
        ("slow", dict(casting=False, backswing_s=0.95, downswing_s=0.32)),
        ("fast", dict(casting=False, backswing_s=0.60, downswing_s=0.19)),
        ("casting", dict(casting=True, backswing_s=0.80, downswing_s=0.27)),
    ]
    tilts = [45.0, 55.0, 65.0]

    cases: list[SwingCase] = []
    for seed in seeds:
        for vname, kwargs in variants:
            tilt = tilts[seed % len(tilts)]
            swing = planar_circular_swing(fs_hz=fs_hz, plane_tilt_deg=tilt, **kwargs)
            for ename, factory in error_levels.items():
                t2, g2, a2, _ = apply_imu_errors(
                    swing.packet.t, swing.packet.gyro, swing.packet.accel, factory(seed)
                )
                cases.append(
                    SwingCase(
                        label=f"{vname}/tilt{int(tilt)}/seed{seed}",
                        swing=swing,
                        gyro=g2,
                        accel=a2,
                        t=t2,
                        error_label=ename,
                        generator="analytic",
                        assumptions={"rigid_fixed_center": True, "family": "analytic_planar"},
                    )
                )
    return cases


def multibody_to_synthetic(truth: SwingTruth) -> SyntheticSwing:
    """Project multibody ground truth onto the SyntheticSwing scoring contract."""
    packet = truth.to_imu_packet()
    ph = truth.phases()
    omega = np.linalg.norm(truth.gyro_body, axis=1)
    alpha = np.linalg.norm(truth.seg_alpha_body[truth.config.mount_segment], axis=1)
    # Approximate swing radius from wrist path span (not used as a hard score
    # when rigid_fixed_center is False).
    pos = truth.sensor_pos - truth.sensor_pos[ph.address_idx]
    radius = float(np.max(np.linalg.norm(pos, axis=1)))
    return SyntheticSwing(
        packet=packet,
        phases_true=ph,
        quats_true=truth.sensor_quat,
        positions_true=truth.sensor_pos,
        velocities_true=truth.sensor_vel,
        angles=truth.seg_angle_rad[truth.config.mount_segment],
        omega_scalar=omega,
        alpha_scalar=alpha,
        peak_omega_time_s=float(truth.t[int(np.argmax(omega))]),
        impact_time_s=float(truth.t[ph.impact_idx]),
        casting=not truth.kinematic_sequence_ok(),
        meta={
            "radius_m": radius,
            "generator": 1.0,
            "club_head_speed_impact_m_s": float(truth.club_head_speed[ph.impact_idx]),
        },
    )


def _inject_impact_shock(
    t: ArrayF,
    quats: ArrayF,
    accel: ArrayF,
    impact_idx: int,
    *,
    impact_shock_g: float = 30.0,
    shock_decay_s: float = 0.012,
    shock_ring_hz: float = 120.0,
) -> ArrayF:
    """Add a broadband strike transient so impact remains physically detectable.

    Multibody kinematics alone are smooth at the impact index; a real club-ball
    collision injects a short high-frequency specific-force spike. Without it,
    high-pass impact detectors are graded against an impossible target.
    """
    if impact_shock_g <= 0.0:
        return accel
    out = accel.copy()
    g = float(np.linalg.norm(so3.G_WORLD))
    tau = t - t[impact_idx]
    ring = np.where(
        tau >= 0.0,
        np.exp(-tau / max(shock_decay_s, 1e-4)) * np.sin(2 * np.pi * shock_ring_hz * tau),
        0.0,
    )
    direction = np.array([0.0, 1.0, 0.3], dtype=np.float64)
    direction /= np.linalg.norm(direction)
    shock_world = impact_shock_g * g * ring[:, None] * direction[None, :]
    for i in range(t.shape[0]):
        out[i] = out[i] + so3.quat_to_rotmat(quats[i]).T @ shock_world[i]
    return out


def build_cases_multibody(
    *,
    seeds: Iterable[int] = (0, 1, 2),
    error_levels: dict[str, Callable[[int], ImuErrorParams]] | None = None,
    fs_hz: float = 200.0,
    violate: bool = False,
    violation_factory: Callable[[int], ViolationSpec] | None = None,
) -> list[SwingCase]:
    """Cross-generator cases from the independent multibody oracle.

    When ``violate`` is True, measurements are further corrupted so the rigid
    lever-arm assumption fails while truth pose/position stay physical.
    """
    if error_levels is None:
        error_levels = {
            "ideal": lambda s: ImuErrorParams.ideal(),
            "consumer": lambda s: ImuErrorParams.consumer_grade(seed=s),
            "harsh": lambda s: ImuErrorParams.harsh(seed=s),
        }
    if violation_factory is None:
        violation_factory = mild_violation

    variants = [
        ("normal", False, 0.80, 0.25),
        ("slow", False, 0.95, 0.32),
        ("fast", False, 0.65, 0.20),
        ("casting", True, 0.80, 0.27),
    ]
    tilts = [45.0, 55.0, 65.0]
    gen_name = "multibody_violate" if violate else "multibody"
    cases: list[SwingCase] = []

    for seed in seeds:
        for vname, casting, bs, ds in variants:
            tilt = tilts[seed % len(tilts)]
            cfg = SwingConfig(
                fs_hz=fs_hz,
                plane_tilt_deg=tilt,
                backswing_s=bs,
                downswing_s=ds,
                address_s=0.35,
                followthrough_s=0.50,
                finish_hold_s=0.20,
            )
            truth = casting_swing(cfg) if casting else build_swing(cfg)
            swing = multibody_to_synthetic(truth)
            gyro0 = truth.gyro_body.copy()
            accel0 = _inject_impact_shock(
                truth.t, truth.sensor_quat, truth.accel_body.copy(), truth.impact_idx
            )
            viol_meta: dict[str, float] = {}
            if violate:
                gyro0, accel0, viol_meta = apply_violations(
                    truth.t,
                    gyro0,
                    accel0,
                    quats_true=truth.sensor_quat,
                    positions_true=truth.sensor_pos,
                    impact_idx=truth.impact_idx,
                    spec=violation_factory(seed),
                )
            for ename, factory in error_levels.items():
                t2, g2, a2, _ = apply_imu_errors(truth.t, gyro0, accel0, factory(seed))
                assumptions: dict[str, float | bool | str] = {
                    "rigid_fixed_center": not violate,
                    "family": "multibody",
                    "violated": violate,
                }
                assumptions.update({f"viol_{k}": v for k, v in viol_meta.items()})
                cases.append(
                    SwingCase(
                        label=f"{gen_name}/{vname}/tilt{int(tilt)}/seed{seed}",
                        swing=swing,
                        gyro=g2,
                        accel=a2,
                        t=t2,
                        error_label=ename,
                        generator=gen_name,
                        assumptions=assumptions,
                    )
                )
    return cases


def benchmark_orientation(cases: list[SwingCase]) -> list[MetricRow]:
    rows: list[MetricRow] = []
    by_alg: dict[tuple[str, str], list[float]] = {}
    by_alg_down: dict[tuple[str, str], list[float]] = {}

    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        bias, _ = ahrs_init.estimate_gyro_bias(case.gyro, case.accel, fs)
        ph = case.swing.phases_true

        # Filters receive raw gyro so that internal bias handling is part of what
        # is being graded. The extra entry is the SciRep-style pipeline: estimate
        # bias on the rest window, then integrate without any accel correction.
        runs: list[tuple[str, ArrayF]] = []
        for est in ahrs_suite.make_default_suite():
            quats, _ = est.run(case.gyro, case.accel, dt, q0=q0)
            runs.append((est.name, quats))
        quats_rb, _ = ahrs_suite.GyroOnly().run(case.gyro - bias, case.accel, dt, q0=q0)
        runs.append(("gyro_only+restbias", quats_rb))

        for name, quats in runs:
            aligned = _yaw_align(quats, case.swing.quats_true, ph.address_idx)
            err = orientation_error_deg(aligned, case.swing.quats_true)
            key = (name, case.error_label)
            by_alg.setdefault(key, []).extend(err.tolist())
            by_alg_down.setdefault(key, []).extend(
                err[ph.top_idx : ph.impact_idx + 1].tolist()
            )

    for (alg, cond), vals in sorted(by_alg.items()):
        m, p, mx, n = _stats(vals)
        rows.append(MetricRow(alg, cond, "orientation_deg_all", m, p, mx, n))
    for (alg, cond), vals in sorted(by_alg_down.items()):
        m, p, mx, n = _stats(vals)
        rows.append(MetricRow(alg, cond, "orientation_deg_downswing", m, p, mx, n))
    return rows


def benchmark_trajectory(cases: list[SwingCase]) -> list[MetricRow]:
    rows: list[MetricRow] = []
    acc: dict[tuple[str, str], list[float]] = {}
    radius_err: dict[str, list[float]] = {}

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
        e_dr = np.linalg.norm(pos_dr[window] - truth[window], axis=1) * 100.0
        acc.setdefault(("dead_reckon_zupt", case.error_label), []).extend(e_dr.tolist())

        la = estimate_lever_arm(quats, gyro_c, case.accel, dt)
        pos_la = la.positions - la.positions[ph.address_idx]
        e_la = np.linalg.norm(pos_la[window] - truth[window], axis=1) * 100.0
        acc.setdefault(("lever_arm", case.error_label), []).extend(e_la.tolist())
        if case.assumptions.get("rigid_fixed_center", True):
            radius_err.setdefault(case.error_label, []).append(
                abs(la.radius_m - case.swing.meta["radius_m"]) * 100.0
            )
        # Always track residual / validity for violation gates
        acc.setdefault(("lever_arm_residual_m_s2", case.error_label), []).append(
            float(la.residual_rms_m_s2)
        )
        acc.setdefault(("lever_arm_invalid", case.error_label), []).append(
            0.0 if la.valid else 1.0
        )

    for (alg, cond), vals in sorted(acc.items()):
        m, p, mx, n = _stats(vals)
        if alg.endswith("_residual_m_s2"):
            metric = "residual_m_s2"
        elif alg.endswith("_invalid"):
            metric = "invalid_rate"
        else:
            metric = "position_cm"
        rows.append(MetricRow(alg, cond, metric, m, p, mx, n))
    for cond, vals in sorted(radius_err.items()):
        m, p, mx, n = _stats(vals)
        rows.append(MetricRow("lever_arm", cond, "radius_err_cm", m, p, mx, n))
    return rows


def benchmark_events(cases: list[SwingCase]) -> list[MetricRow]:
    rows: list[MetricRow] = []
    acc: dict[tuple[str, str], list[float]] = {}
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
            acc.setdefault((name, case.error_label), []).append(err_ms)

    for (name, cond), vals in sorted(acc.items()):
        m, p, mx, n = _stats(vals)
        rows.append(
            MetricRow(
                f"event_{name}",
                cond,
                "abs_error_ms",
                m,
                p,
                mx,
                n,
                extra={"failures": float(failures.get(cond, 0))},
            )
        )
    return rows


def benchmark_session(
    seeds: Iterable[int] = (0, 1),
    n_swings: int = 8,
    rest_between_s: float = 3.0,
) -> list[MetricRow]:
    """Long multi-swing session: the regime where gyro drift actually bites."""
    from golfmate_algo.synth.session import make_session

    rows: list[MetricRow] = []
    acc: dict[tuple[str, str], list[float]] = {}
    levels = {
        "consumer": ImuErrorParams.consumer_grade,
        "harsh": ImuErrorParams.harsh,
    }

    for seed in seeds:
        session = make_session(n_swings=n_swings, rest_between_s=rest_between_s, seed=seed)
        fs = session.packet.frame.fs_hz
        dt = 1.0 / fs
        for lname, factory in levels.items():
            _, gyro, accel, _ = apply_imu_errors(
                session.packet.t, session.packet.gyro, session.packet.accel, factory(seed)
            )
            q0, _, _ = ahrs_init.estimate_address_orientation(gyro, accel, fs)
            bias, _ = ahrs_init.estimate_gyro_bias(gyro, accel, fs)

            runs: list[tuple[str, ArrayF]] = []
            for est in ahrs_suite.make_default_suite():
                quats, _ = est.run(gyro, accel, dt, q0=q0)
                runs.append((est.name, quats))
            q_rb, _ = ahrs_suite.GyroOnly().run(gyro - bias, accel, dt, q0=q0)
            runs.append(("gyro_only+restbias", q_rb))

            for name, quats in runs:
                aligned = _yaw_align(quats, session.quats_true, 0)
                err = orientation_error_deg(aligned, session.quats_true)
                acc.setdefault((name, lname), []).extend(err.tolist())

    for (alg, cond), vals in sorted(acc.items()):
        m, p, mx, n = _stats(vals)
        rows.append(MetricRow(alg, f"session/{cond}", "orientation_deg_session", m, p, mx, n))
    return rows


def format_rows(rows: list[MetricRow]) -> str:
    header = f"{'algorithm':<26}{'condition':<12}{'metric':<28}{'mean':>10}{'p95':>10}{'max':>10}{'n':>7}"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.algorithm:<26}{r.condition:<12}{r.metric:<28}"
            f"{r.mean:>10.3f}{r.p95:>10.3f}{r.maximum:>10.3f}{r.n:>7d}"
        )
    return "\n".join(lines)


def run_all(seeds: Iterable[int] = (0, 1, 2), include_session: bool = True) -> list[MetricRow]:
    cases = build_cases(seeds=seeds)
    rows = (
        benchmark_orientation(cases)
        + benchmark_trajectory(cases)
        + benchmark_events(cases)
    )
    if include_session:
        rows += benchmark_session()
    return rows


if __name__ == "__main__":  # pragma: no cover
    print(format_rows(run_all()))
