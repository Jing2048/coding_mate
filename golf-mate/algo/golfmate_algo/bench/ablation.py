"""Ablation and degradation suites for gated AHRS + trajectory.

These isolate *why* the chosen pipeline wins, not just that it wins:
  - gate terms (a / ω / α) and rest-hard gate
  - trajectory reconstructors
  - sensor-error magnitude scaling (degradation curves)
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs.suite import DynamicsGate, GatedAdaptive, GyroOnly
from golfmate_algo.bench.harness import (
    SwingCase,
    _yaw_align,
    orientation_error_deg,
)
from golfmate_algo.bench.stats import Summary, summarize
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.session import make_session
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm

ArrayF = NDArray[np.float64]


def _mean_orient_err(
    quats: ArrayF,
    q_true: ArrayF,
    address_idx: int = 0,
    window: slice | None = None,
) -> float:
    aligned = _yaw_align(quats, q_true, address_idx)
    err = orientation_error_deg(aligned, q_true)
    if window is not None:
        err = err[window]
    return float(np.mean(err))


# --------------------------------------------------------------------------- gate ablations


def _gate_variants() -> list[tuple[str, DynamicsGate | None, bool]]:
    """(label, gate, require_rest). None gate means always-open accel trust."""
    return [
        ("full_gate+rest", DynamicsGate(), True),
        ("no_alpha", DynamicsGate(sigma_alpha=1e9), True),
        ("a_only", DynamicsGate(sigma_w=1e9, sigma_alpha=1e9), True),
        ("no_rest_hard", DynamicsGate(), False),
        ("always_open", None, False),
        ("gyro_only", None, True),  # rest=True but gate disabled → pure integrate
    ]


class _AblationFilter(GatedAdaptive):
    """GatedAdaptive with injectable gate / rest policy for fair ablations."""

    name = "ablation"

    def __init__(
        self,
        *,
        gate: DynamicsGate | None,
        require_rest: bool,
        disable_accel: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(gate=gate or DynamicsGate(), **kwargs)
        self._gate_obj = gate
        self._require_rest = require_rest
        self._disable_accel = disable_accel

    def update(self, gyro, accel, dt):  # type: ignore[override]
        from golfmate_algo.ahrs.suite import (
            G_NORM,
            _apply_world_tilt_correction,
            _as_vec3,
            _safe_dt,
        )
        from golfmate_algo.math import so3

        gyro_v, accel_v, dt_s = _as_vec3(gyro), _as_vec3(accel), _safe_dt(dt)
        a_norm = float(np.linalg.norm(accel_v))
        w_norm = float(np.linalg.norm(gyro_v))
        alpha_norm = 0.0
        if self._prev_gyro is not None and dt_s > 0:
            alpha_norm = float(np.linalg.norm(gyro_v - self._prev_gyro) / dt_s)
        self._prev_gyro = gyro_v.copy()

        rest = (
            abs(a_norm - G_NORM) <= self.rest_accel_tol_g * G_NORM
            and w_norm <= self.rest_gyro_thresh
        )
        if rest and self.bias_tau_s > 0.0 and dt_s > 0.0:
            self.bias += (1.0 - float(np.exp(-dt_s / self.bias_tau_s))) * (gyro_v - self.bias)

        q_pred = so3.integrate_gyro_rk4(self.q, gyro_v - self.bias, dt_s)
        if self._disable_accel:
            gate = 0.0
        elif self._gate_obj is None:
            gate = 1.0 if (rest or not self._require_rest) else 0.0
            if not self._require_rest:
                gate = 1.0
        else:
            raw = self._gate_obj(w_norm, a_norm, alpha_norm)
            gate = raw if (rest or not self._require_rest) else 0.0
            if self._require_rest and not rest:
                gate = 0.0

        alpha = 1.0 - float(np.exp(-max(self.tilt_gain, 0.0) * gate * dt_s))
        self.q = _apply_world_tilt_correction(q_pred, accel_v, alpha)
        self.gate_history.append(gate)
        self.bias_history.append(self.bias.copy())
        self.rest_history.append(bool(rest))
        return self.q.copy()


def benchmark_gate_ablation(
    cases: list[SwingCase],
    *,
    n_boot: int = 1500,
) -> dict[str, dict[str, Summary]]:
    """Mean orientation error (°), stratified by error level × gate variant."""
    buckets: dict[tuple[str, str], list[float]] = {}

    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        ph = case.swing.phases_true
        down = slice(ph.top_idx, ph.impact_idx + 1)

        for label, gate, require_rest in _gate_variants():
            disable = label == "gyro_only"
            est = _AblationFilter(
                gate=gate, require_rest=require_rest, disable_accel=disable
            )
            est.name = label
            quats, _ = est.run(case.gyro, case.accel, dt, q0=q0)
            err_all = _mean_orient_err(quats, case.swing.quats_true, ph.address_idx)
            err_down = _mean_orient_err(
                quats, case.swing.quats_true, ph.address_idx, window=down
            )
            buckets.setdefault((label, case.error_label + "/all"), []).append(err_all)
            buckets.setdefault((label, case.error_label + "/down"), []).append(err_down)

    out: dict[str, dict[str, Summary]] = {}
    for (alg, cond), vals in sorted(buckets.items()):
        out.setdefault(alg, {})[cond] = summarize(vals, n_boot=n_boot, seed=hash(alg) % 10_000)
    return out


def benchmark_gate_ablation_session(
    seeds: list[int] | tuple[int, ...] = (0, 1, 2, 3),
    *,
    n_boot: int = 1500,
) -> dict[str, dict[str, Summary]]:
    """Session-scale ablation: where rest+gate actually pays rent."""
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
            for label, gate, require_rest in _gate_variants():
                disable = label == "gyro_only"
                est = _AblationFilter(
                    gate=gate, require_rest=require_rest, disable_accel=disable
                )
                quats, _ = est.run(gyro, accel, dt, q0=q0)
                err = _mean_orient_err(quats, session.quats_true, 0)
                buckets.setdefault((label, f"session/{lname}"), []).append(err)

    out: dict[str, dict[str, Summary]] = {}
    for (alg, cond), vals in sorted(buckets.items()):
        out.setdefault(alg, {})[cond] = summarize(vals, n_boot=n_boot, seed=hash(alg) % 10_000)
    return out


# --------------------------------------------------------------------------- trajectory ablation


def benchmark_traj_ablation(
    cases: list[SwingCase],
    *,
    n_boot: int = 1500,
) -> dict[str, dict[str, Summary]]:
    buckets: dict[tuple[str, str], list[float]] = {}
    for case in cases:
        fs = case.swing.packet.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(case.gyro, case.accel, fs)
        bias, _ = ahrs_init.estimate_gyro_bias(case.gyro, case.accel, fs)
        gyro_c = case.gyro - bias
        quats, _ = GatedAdaptive().run(gyro_c, case.accel, dt, q0=q0)
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

        # Oracle orientation: isolates trajectory method from AHRS error
        q_true = case.swing.quats_true
        la_o = estimate_lever_arm(q_true, case.swing.packet.gyro, case.swing.packet.accel, dt)
        pos_o = la_o.positions - la_o.positions[ph.address_idx]
        e_o = float(np.mean(np.linalg.norm(pos_o[window] - truth[window], axis=1) * 100.0))
        buckets.setdefault(("lever_arm_oracle_R", case.error_label), []).append(e_o)

    out: dict[str, dict[str, Summary]] = {}
    for (alg, cond), vals in sorted(buckets.items()):
        out.setdefault(alg, {})[cond] = summarize(vals, n_boot=n_boot, seed=11)
    return out


# --------------------------------------------------------------------------- degradation curves


def _scale_consumer(scale: float, seed: int) -> ImuErrorParams:
    """Scale stochastic + bias terms of consumer-grade model by ``scale``."""
    base = ImuErrorParams.consumer_grade(seed=seed)
    return replace(
        base,
        gyro_arw_deg_s_sqrt_hz=base.gyro_arw_deg_s_sqrt_hz * scale,
        accel_vrw_m_s2_sqrt_hz=base.accel_vrw_m_s2_sqrt_hz * scale,
        gyro_bias_const_deg_s=base.gyro_bias_const_deg_s * scale,
        accel_bias_const_m_s2=base.accel_bias_const_m_s2 * scale,
        gyro_bias_rw_deg_s_sqrt_s=base.gyro_bias_rw_deg_s_sqrt_s * scale,
        accel_bias_rw_m_s2_sqrt_s=base.accel_bias_rw_m_s2_sqrt_s * scale,
        mount_gain=min(0.5, base.mount_gain * scale),
        misalignment_deg=base.misalignment_deg * scale,
    )


def benchmark_degradation(
    *,
    scales: list[float] | None = None,
    seeds: list[int] | tuple[int, ...] = (0, 1, 2, 3, 4),
    n_boot: int = 1000,
) -> dict[str, list[dict[str, float]]]:
    """Orientation mean error vs noise scale for gated vs gyro-only (single + session)."""
    if scales is None:
        scales = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]

    single_rows: list[dict[str, float]] = []
    session_rows: list[dict[str, float]] = []

    for scale in scales:
        single_g: list[float] = []
        single_o: list[float] = []
        sess_g: list[float] = []
        sess_o: list[float] = []

        for seed in seeds:
            swing = planar_circular_swing(
                fs_hz=200.0,
                plane_tilt_deg=[45.0, 55.0, 65.0][seed % 3],
                casting=bool(seed % 2),
            )
            params = _scale_consumer(scale, seed)
            t2, g2, a2, _ = apply_imu_errors(
                swing.packet.t, swing.packet.gyro, swing.packet.accel, params
            )
            fs = swing.packet.frame.fs_hz
            dt = 1.0 / fs
            q0, _, _ = ahrs_init.estimate_address_orientation(g2, a2, fs)
            qg, _ = GatedAdaptive().run(g2, a2, dt, q0=q0)
            qo, _ = GyroOnly().run(g2, a2, dt, q0=q0)
            single_g.append(_mean_orient_err(qg, swing.quats_true, swing.phases_true.address_idx))
            single_o.append(_mean_orient_err(qo, swing.quats_true, swing.phases_true.address_idx))

            session = make_session(n_swings=6, rest_between_s=2.5, seed=seed)
            _, gs, as_, _ = apply_imu_errors(
                session.packet.t, session.packet.gyro, session.packet.accel, params
            )
            fs_s = session.packet.frame.fs_hz
            dt_s = 1.0 / fs_s
            q0s, _, _ = ahrs_init.estimate_address_orientation(gs, as_, fs_s)
            qgs, _ = GatedAdaptive().run(gs, as_, dt_s, q0=q0s)
            qos, _ = GyroOnly().run(gs, as_, dt_s, q0=q0s)
            sess_g.append(_mean_orient_err(qgs, session.quats_true, 0))
            sess_o.append(_mean_orient_err(qos, session.quats_true, 0))

        sg = summarize(single_g, n_boot=n_boot, seed=int(scale * 100))
        so = summarize(single_o, n_boot=n_boot, seed=int(scale * 100) + 1)
        ssg = summarize(sess_g, n_boot=n_boot, seed=int(scale * 100) + 2)
        sso = summarize(sess_o, n_boot=n_boot, seed=int(scale * 100) + 3)
        single_rows.append(
            {
                "scale": scale,
                "gated_mean": sg.mean,
                "gated_ci_lo": sg.ci95_lo,
                "gated_ci_hi": sg.ci95_hi,
                "gyro_only_mean": so.mean,
                "gyro_only_ci_lo": so.ci95_lo,
                "gyro_only_ci_hi": so.ci95_hi,
            }
        )
        session_rows.append(
            {
                "scale": scale,
                "gated_mean": ssg.mean,
                "gated_ci_lo": ssg.ci95_lo,
                "gated_ci_hi": ssg.ci95_hi,
                "gyro_only_mean": sso.mean,
                "gyro_only_ci_lo": sso.ci95_lo,
                "gyro_only_ci_hi": sso.ci95_hi,
            }
        )

    return {"single_swing": single_rows, "session": session_rows}
