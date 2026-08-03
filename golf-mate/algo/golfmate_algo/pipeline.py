"""End-to-end P0/P0.5 pipeline: IMU packet -> SwingReport.

Default path uses dual-path signals, CROP-lite residual bias correction,
gated-adaptive AHRS with signed-log tilt, offline endpoint SO(3) anchors,
and hybrid constrained trajectory.
See ``docs/research/06_zero_trust_benchmark.md`` for graded numbers.
"""

from __future__ import annotations

import numpy as np

from golfmate_algo.ahrs import init as ahrs_init
from golfmate_algo.ahrs.offline_smooth import smooth_endpoint_anchors
from golfmate_algo.ahrs.suite import GatedAdaptive
from golfmate_algo.biomechanics.proxies import estimate_biomech_proxies
from golfmate_algo.biomechanics.sequence import sequence_proxy
from golfmate_algo.calib.crop_lite import crop_lite_correct
from golfmate_algo.coach.diagnostics import diagnose
from golfmate_algo.devices.normalize import normalize_packet
from golfmate_algo.events.segmental import detect_phases_segmental
from golfmate_algo.features.wrist import compute_wrist_features
from golfmate_algo.math import so3
from golfmate_algo.reference.score import reference_finding, score_against_reference
from golfmate_algo.signal.dynamic_range import split_dual_path
from golfmate_algo.traj.dead_reckon import reconstruct_trajectory
from golfmate_algo.traj.hybrid import estimate_hybrid_trajectory
from golfmate_algo.traj.lever_arm import estimate_lever_arm
from golfmate_algo.types import ImuPacket, SwingReport


def analyze_swing(
    packet: ImuPacket,
    *,
    trajectory: str = "hybrid",
    prefer_vqf: bool = False,
    use_crop_lite: bool = True,
    use_dual_path: bool = True,
    compare_to_ideal: bool = True,
    use_offline_smooth: bool = False,
) -> SwingReport:
    """Run the full analysis pipeline.

    Parameters
    ----------
    trajectory :
        ``"hybrid"`` (default) varying-centre lever + event constraints + plane
        closure; ``"lever_arm"`` rigid baseline; ``"dead_reckon"`` ZUPT integrate.

    The packet is first passed through ``normalize_packet`` so Watch / glove /
    left-handed streams share one canonical lead-right anatomical frame.
    Irregular timestamps are resampled to a fixed grid inside normalize.
    """
    del prefer_vqf
    packet, norm_info = normalize_packet(packet)
    fs = packet.frame.fs_hz
    dt = 1.0 / fs

    dual = split_dual_path(packet.gyro, packet.accel, fs) if use_dual_path else None
    gyro_work = dual.gyro if dual is not None else packet.gyro
    accel_raw = dual.accel_raw if dual is not None else packet.accel
    accel_ahrs = dual.accel_ahrs if dual is not None else packet.accel

    # Coarse phases on raw accel (need impact shock), then CROP on rest windows
    phases_coarse, seg_coarse = detect_phases_segmental(
        packet.t, gyro_work, accel_raw, return_diagnostics=True
    )
    crop_meta: dict[str, float] = {}
    if use_crop_lite:
        crop = crop_lite_correct(
            gyro_work,
            accel_raw,
            fs,
            address_idx=phases_coarse.address_idx,
            finish_idx=phases_coarse.finish_idx,
        )
        gyro_work = crop.gyro_corr
        accel_raw = crop.accel_corr
        if dual is not None:
            from golfmate_algo.signal.dynamic_range import signed_log_compress

            # Keep dual-path meta / diagnostics; AHRS still compresses once internally.
            accel_ahrs = signed_log_compress(accel_raw)
        else:
            accel_ahrs = accel_raw
        crop_meta = {
            "crop_success": float(crop.success),
            "crop_cost": float(crop.cost) if np.isfinite(crop.cost) else -1.0,
            "crop_rest_fraction": float(crop.rest_fraction),
            "crop_delta_gyro_norm": float(np.linalg.norm(crop.delta_gyro)),
            "crop_delta_accel_norm": float(np.linalg.norm(crop.delta_accel)),
        }

    q0, addr_window, init_quality = ahrs_init.estimate_address_orientation(
        gyro_work, accel_raw, fs, use_signed_log=True
    )
    # AHRS: integrate corrected gyro; tilt uses signed-log once inside the filter
    # (do not pre-compress accel_ahrs here — that would double-compress).
    quats, ahrs_diag = GatedAdaptive(use_signed_log_tilt=True).run(
        gyro_work, accel_raw, dt, q0=q0
    )
    gyro_bias = (
        ahrs_diag["bias"][-1] if len(ahrs_diag.get("bias", [])) else np.zeros(3)
    )
    gyro_c = gyro_work - gyro_bias

    # Final phases on corrected raw accel
    phases, seg_diag = detect_phases_segmental(
        packet.t, gyro_c, accel_raw, return_diagnostics=True
    )

    # Offline anchors only when address is a trusted rest AND tilt is wrong.
    # Consumer accel noise can look like a large tilt error even when the AHRS
    # track is already within a few degrees of truth — gating prevents that.
    smooth_meta: dict[str, float] = {}
    if use_offline_smooth:
        from golfmate_algo.ahrs.suite import DynamicsGate

        a_idx = int(phases.address_idx)
        lo = max(0, a_idx - max(2, int(0.04 / dt)))
        hi = min(len(accel_raw), a_idx + max(2, int(0.04 / dt)) + 1)
        g_win = gyro_c[lo:hi]
        a_win = accel_raw[lo:hi]
        g_n = float(np.mean(np.linalg.norm(g_win, axis=1)))
        a_n = float(np.mean(np.linalg.norm(a_win, axis=1)))
        alpha = (
            float(np.mean(np.linalg.norm(np.diff(g_win, axis=0), axis=1) / dt))
            if g_win.shape[0] >= 2
            else 0.0
        )
        trust = DynamicsGate()(g_n, a_n, alpha)
        R = so3.quat_to_rotmat(quats[a_idx])
        up_b = -R.T @ so3.G_WORLD
        up_b = up_b / (np.linalg.norm(up_b) + 1e-12)
        a_hat = np.mean(a_win, axis=0)
        a_hat = a_hat / (np.linalg.norm(a_hat) + 1e-12)
        tilt_err_deg = float(
            np.degrees(np.arccos(float(np.clip(np.dot(up_b, a_hat), -1.0, 1.0))))
        )
        if trust >= 0.55 and tilt_err_deg >= 4.0:
            sm = smooth_endpoint_anchors(
                quats,
                gyro_c,
                accel_raw,
                dt,
                address_idx=phases.address_idx,
                finish_idx=phases.finish_idx,
            )
            quats = sm.quats
            smooth_meta = {
                "offline_smooth_applied": float(sm.applied),
                "offline_addr_tilt_corr_deg": float(sm.addr_tilt_corr_deg),
                "offline_fin_tilt_corr_deg": float(sm.fin_tilt_corr_deg),
                "offline_pre_tilt_err_deg": tilt_err_deg,
                "offline_rest_trust": trust,
            }
        else:
            smooth_meta = {
                "offline_smooth_applied": 0.0,
                "offline_pre_tilt_err_deg": tilt_err_deg,
                "offline_rest_trust": trust,
                "offline_skipped_good_tilt": 1.0,
            }

    traj_meta: dict[str, float] = {}
    if trajectory == "hybrid":
        hy = estimate_hybrid_trajectory(quats, gyro_c, accel_raw, dt, phases)
        pos, vel = hy.positions, hy.velocities
        traj_meta = {
            "radius_m": hy.radius_m,
            "residual_rms_m_s2": hy.residual_rms_m_s2,
            "rank": float(hy.rank),
            "valid": float(hy.valid),
            "blend_w_lever": hy.blend_w_lever,
            "plane_residual_rms": hy.plane_residual_rms,
            "circle_residual_rms": hy.circle_residual_rms,
            "center_harmonics": float(hy.center_harmonics),
            "fallback": float(hy.fallback),
            **hy.meta,
        }
    elif trajectory == "lever_arm":
        la = estimate_lever_arm(quats, gyro_c, accel_raw, dt)
        pos, vel = la.positions, la.velocities
        traj_meta = {
            "radius_m": la.radius_m,
            "residual_rms_m_s2": la.residual_rms_m_s2,
            "rank": float(la.rank),
            "valid": float(la.valid),
        }
        if not la.valid:
            _, vel, pos = reconstruct_trajectory(quats, accel_raw, dt, phases=phases)
            traj_meta["fallback"] = 1.0
    else:
        _, vel, pos = reconstruct_trajectory(quats, accel_raw, dt, phases=phases)

    pos = pos - pos[phases.address_idx]
    features = compute_wrist_features(packet.t, gyro_c, quats, vel, pos, phases)
    proxies = estimate_biomech_proxies(packet.t, gyro_c, phases)
    features.extras.update(
        {
            "x_factor_proxy_deg": proxies.x_factor_proxy_deg,
            "pelvis_peak_to_impact_s": proxies.pelvis_peak_to_impact_s,
            "torso_peak_to_impact_s": proxies.torso_peak_to_impact_s,
            "sequence_score_proxy": proxies.sequence_score,
            "proxy_confidence": proxies.confidence,
        }
    )
    findings = diagnose(features)
    seq = sequence_proxy(packet.t, gyro_c, phases)

    ref_meta: dict = {}
    if compare_to_ideal:
        from golfmate_algo.types import SwingReport as _SR

        _tmp = _SR(
            phases=phases,
            features=features,
            findings=findings,
            quats=quats,
            positions=pos,
            velocities=vel,
            gate_open=np.asarray(ahrs_diag.get("gate", []), dtype=np.float64),
        )
        ref_score = score_against_reference(_tmp)
        findings = list(findings) + [reference_finding(ref_score)]
        ref_meta = {
            "reference_score": {
                "overall": ref_score.overall,
                "confidence": ref_score.confidence,
                "template_version": ref_score.template_version,
                "is_proxy": True,
                "per_feature": ref_score.per_feature,
            },
        }

    return SwingReport(
        phases=phases,
        features=features,
        findings=findings,
        quats=quats,
        positions=pos,
        velocities=vel,
        gate_open=np.asarray(ahrs_diag.get("gate", []), dtype=np.float64),
        meta={
            "backend": "gated_adaptive+offline_anchors",
            "trajectory": trajectory,
            "gyro_bias": np.asarray(gyro_bias, dtype=np.float64).tolist(),
            "address_init_quality": init_quality.get("quality", "unknown"),
            "address_window": [addr_window.start, addr_window.stop],
            "sequence_proxy": {
                "wrist_peak_idx": seq.wrist_peak_idx,
                "wrist_peak_to_impact_s": seq.wrist_peak_to_impact_s,
            },
            "biomech_proxies": {
                "x_factor_proxy_deg": proxies.x_factor_proxy_deg,
                "sequence_score": proxies.sequence_score,
                "confidence": proxies.confidence,
                "is_proxy": True,
            },
            "impact_mode": seg_diag.impact_mode,
            "impact_confidence": float(seg_diag.impact_confidence),
            "impact_method": seg_diag.method,
            "coarse_impact_mode": seg_coarse.impact_mode,
            **ref_meta,
            "fs_hz": fs,
            "device_id": packet.frame.device_id,
            "frame": {
                "handedness": packet.frame.handedness.value,
                "wrist": packet.frame.wrist.value,
                "is_canonical": bool(packet.frame.is_canonical),
                "source_handedness": norm_info.source_handedness,
                "source_wrist": norm_info.source_wrist,
                "applied_extrinsic": float(norm_info.applied_extrinsic),
                "applied_mirror": float(norm_info.applied_mirror),
                "applied_resample": float(norm_info.applied_resample),
            },
            "dual_path": dual.meta if dual is not None else {},
            "accel_ahrs_precompressed": float(
                dual is not None and not np.allclose(accel_ahrs, accel_raw)
            ),
            **crop_meta,
            **smooth_meta,
            **traj_meta,
        },
    )
