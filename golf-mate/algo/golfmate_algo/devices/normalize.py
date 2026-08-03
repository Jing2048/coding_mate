"""Normalize ImuPacket into the canonical lead-right anatomical frame."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from golfmate_algo.devices.mirror import apply_linear_map, mirror_matrix, needs_mirror
from golfmate_algo.math import so3
from golfmate_algo.signal.resample import ensure_fixed_rate_packet, resample_packet
from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, WristSide

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class NormalizationInfo:
    applied_extrinsic: bool
    applied_mirror: bool
    applied_resample: bool
    source_handedness: str
    source_wrist: str
    source_device_id: str
    already_canonical: bool


def _is_identity_quat(q: tuple[float, float, float, float], tol: float = 1e-9) -> bool:
    qn = so3.normalize_quat(q)
    # Identity or equivalent sign flip
    return bool(abs(abs(qn[0]) - 1.0) < tol and abs(qn[1]) < tol and abs(qn[2]) < tol and abs(qn[3]) < tol)


def normalize_packet(
    packet: ImuPacket,
    *,
    target_fs_hz: float | None = None,
) -> tuple[ImuPacket, NormalizationInfo]:
    """Map a device-frame packet into the canonical algorithm frame.

    Steps
    -----
    1. Short-circuit if ``frame.is_canonical``.
    2. Apply ``mount_extrinsic`` (sensor body → wrist anatomy).
    3. Mirror axes for left-handed / trail-wrist into lead-right anatomy.
    4. Optionally resample to ``target_fs_hz``.
    5. Rewrite frame metadata to canonical defaults and set ``is_canonical``.
    """
    frame = packet.frame
    info = NormalizationInfo(
        applied_extrinsic=False,
        applied_mirror=False,
        applied_resample=False,
        source_handedness=frame.handedness.value,
        source_wrist=frame.wrist.value,
        source_device_id=frame.device_id,
        already_canonical=bool(frame.is_canonical),
    )
    if frame.is_canonical:
        if target_fs_hz is not None and abs(frame.fs_hz - target_fs_hz) > 1e-6:
            out = resample_packet(packet.t, packet.gyro, packet.accel, target_fs_hz, frame=frame)
            # Preserve canonical flag
            out = ImuPacket(
                frame=SensorFrame(
                    fs_hz=target_fs_hz,
                    wrist=WristSide.LEAD,
                    handedness=Handedness.RIGHT,
                    mount_extrinsic=_IDENTITY_QUAT,
                    device_id=frame.device_id,
                    is_canonical=True,
                ),
                t=out.t,
                gyro=out.gyro,
                accel=out.accel,
            )
            info = NormalizationInfo(
                applied_extrinsic=False,
                applied_mirror=False,
                applied_resample=True,
                source_handedness=info.source_handedness,
                source_wrist=info.source_wrist,
                source_device_id=info.source_device_id,
                already_canonical=True,
            )
            return out, info
        out, jitter_rs = ensure_fixed_rate_packet(packet)
        if jitter_rs:
            info = NormalizationInfo(
                applied_extrinsic=False,
                applied_mirror=False,
                applied_resample=True,
                source_handedness=info.source_handedness,
                source_wrist=info.source_wrist,
                source_device_id=info.source_device_id,
                already_canonical=True,
            )
            return out, info
        return packet, info

    gyro = np.asarray(packet.gyro, dtype=np.float64).copy()
    accel = np.asarray(packet.accel, dtype=np.float64).copy()
    applied_ext = False
    applied_mir = False

    if not _is_identity_quat(frame.mount_extrinsic):
        R = so3.quat_to_rotmat(frame.mount_extrinsic)
        # mount_extrinsic: sensor body → wrist anatomy
        gyro = (R @ gyro.T).T
        accel = (R @ accel.T).T
        applied_ext = True

    if needs_mirror(frame.handedness, frame.wrist):
        m = mirror_matrix(frame.handedness, frame.wrist)
        gyro = apply_linear_map(gyro, m)
        accel = apply_linear_map(accel, m)
        applied_mir = True

    applied_rs = False
    fs = float(frame.fs_hz)
    t = np.asarray(packet.t, dtype=np.float64)
    if target_fs_hz is not None and abs(fs - target_fs_hz) > 1e-6:
        tmp = resample_packet(
            t,
            gyro,
            accel,
            target_fs_hz,
            frame=SensorFrame(fs_hz=fs, device_id=frame.device_id),
        )
        t, gyro, accel = tmp.t, tmp.gyro, tmp.accel
        fs = float(target_fs_hz)
        applied_rs = True

    out = ImuPacket(
        frame=SensorFrame(
            fs_hz=fs,
            wrist=WristSide.LEAD,
            handedness=Handedness.RIGHT,
            mount_extrinsic=_IDENTITY_QUAT,
            device_id=frame.device_id,
            is_canonical=True,
        ),
        t=t,
        gyro=gyro,
        accel=accel,
    )
    # Irregular timestamps (mocap / BLE jitter) must not reach strapdown with a
    # single median dt — enforce a true fixed-rate grid.
    out, jitter_rs = ensure_fixed_rate_packet(out, target_fs_hz=target_fs_hz)
    applied_rs = applied_rs or jitter_rs
    fs = float(out.frame.fs_hz)
    info = NormalizationInfo(
        applied_extrinsic=applied_ext,
        applied_mirror=applied_mir,
        applied_resample=applied_rs,
        source_handedness=frame.handedness.value,
        source_wrist=frame.wrist.value,
        source_device_id=frame.device_id,
        already_canonical=False,
    )
    return out, info
