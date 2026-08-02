"""End-to-end P0 pipeline: IMU packet → SwingReport."""

from __future__ import annotations

from golfmate_algo.ahrs.gated_vqf import GolfGatedAHRS
from golfmate_algo.biomechanics.sequence import sequence_proxy
from golfmate_algo.calib.static import apply_gyro_bias, rest_bias
from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.events.phase import detect_phases
from golfmate_algo.features.wrist import compute_wrist_features
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.types import ImuPacket, SwingReport


def analyze_swing(
    packet: ImuPacket,
    *,
    prefer_vqf: bool = True,
    rest_bias_samples: int = 40,
) -> SwingReport:
    fs = packet.frame.fs_hz
    dt = 1.0 / fs
    bias = rest_bias(packet.gyro, n=rest_bias_samples)
    gyro = apply_gyro_bias(packet.gyro, bias)

    ahrs = GolfGatedAHRS(fs_hz=fs, prefer_vqf=prefer_vqf)
    # Initialize from first sample gravity if complementary; VQF warms up online
    quats, gate = ahrs.batch_process(gyro, packet.accel, dt)

    phases = detect_phases(packet.t, gyro, packet.accel)
    _, vel, pos = reconstruct_trajectory(quats, packet.accel, dt, phases=phases)
    features = compute_wrist_features(
        packet.t, gyro, quats, vel, pos, phases
    )
    findings = diagnose(features)
    seq = sequence_proxy(packet.t, gyro, phases)

    return SwingReport(
        phases=phases,
        features=features,
        findings=findings,
        quats=quats,
        positions=pos,
        velocities=vel,
        gate_open=gate,
        meta={
            "backend": ahrs.backend_name,
            "gyro_bias": bias.tolist(),
            "sequence_proxy": {
                "wrist_peak_idx": seq.wrist_peak_idx,
                "wrist_peak_to_impact_s": seq.wrist_peak_to_impact_s,
            },
            "fs_hz": fs,
        },
    )
