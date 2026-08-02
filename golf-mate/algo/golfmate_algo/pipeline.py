"""End-to-end P0 pipeline: IMU packet -> SwingReport.

The component choices here are the ones that won the benchmark in
``golfmate_algo.bench.harness``; see ``docs/research/04_benchmark.md`` for the
numbers and the reasoning.
"""

from __future__ import annotations

import numpy as np

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs.suite import GatedAdaptive
from golfmate_algo.biomechanics.sequence import sequence_proxy
from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.features.wrist import compute_wrist_features
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.types import ImuPacket, SwingReport


def analyze_swing(
    packet: ImuPacket,
    *,
    trajectory: str = "lever_arm",
    prefer_vqf: bool = False,
) -> SwingReport:
    """Run the full P0 analysis.

    Parameters
    ----------
    trajectory : ``"lever_arm"`` uses the rigid-rotation solve, which does not
        accumulate double-integration drift; ``"dead_reckon"`` selects the
        classical integrate-and-ZUPT baseline retained for comparison.
    """
    del prefer_vqf  # retained for call-site compatibility; VQF is not required
    fs = packet.frame.fs_hz
    dt = 1.0 / fs

    q0, addr_window, init_quality = ahrs_init.estimate_address_orientation(
        packet.gyro, packet.accel, fs
    )
    quats, ahrs_diag = GatedAdaptive().run(packet.gyro, packet.accel, dt, q0=q0)
    gyro_bias = (
        ahrs_diag["bias"][-1] if len(ahrs_diag.get("bias", [])) else np.zeros(3)
    )
    gyro_c = packet.gyro - gyro_bias

    phases = detect_phases_segmental(packet.t, packet.gyro, packet.accel)

    traj_meta: dict[str, float] = {}
    if trajectory == "lever_arm":
        la = estimate_lever_arm(quats, gyro_c, packet.accel, dt)
        pos, vel = la.positions, la.velocities
        traj_meta = {
            "radius_m": la.radius_m,
            "residual_rms_m_s2": la.residual_rms_m_s2,
            "rank": float(la.rank),
            "valid": float(la.valid),
        }
        if not la.valid:
            _, vel, pos = reconstruct_trajectory(quats, packet.accel, dt, phases=phases)
            traj_meta["fallback"] = 1.0
    else:
        _, vel, pos = reconstruct_trajectory(quats, packet.accel, dt, phases=phases)

    pos = pos - pos[phases.address_idx]
    features = compute_wrist_features(packet.t, gyro_c, quats, vel, pos, phases)
    findings = diagnose(features)
    seq = sequence_proxy(packet.t, gyro_c, phases)

    return SwingReport(
        phases=phases,
        features=features,
        findings=findings,
        quats=quats,
        positions=pos,
        velocities=vel,
        gate_open=np.asarray(ahrs_diag.get("gate", []), dtype=np.float64),
        meta={
            "backend": "gated_adaptive",
            "trajectory": trajectory,
            "gyro_bias": np.asarray(gyro_bias, dtype=np.float64).tolist(),
            "address_init_quality": init_quality.get("quality", "unknown"),
            "address_window": [addr_window.start, addr_window.stop],
            "sequence_proxy": {
                "wrist_peak_idx": seq.wrist_peak_idx,
                "wrist_peak_to_impact_s": seq.wrist_peak_to_impact_s,
            },
            "fs_hz": fs,
            **traj_meta,
        },
    )
