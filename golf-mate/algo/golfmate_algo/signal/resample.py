"""Resample irregular IMU streams to a fixed grid."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.types import ImuPacket, SensorFrame

ArrayF = NDArray[np.float64]


def timestamp_jitter_cv(t: ArrayLike) -> float:
    """Coefficient of variation of positive inter-sample intervals."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if t.size < 3:
        return 0.0
    dts = np.diff(t)
    dts = dts[dts > 0]
    if dts.size < 2:
        return 0.0
    med = float(np.median(dts))
    if med <= 0:
        return float("inf")
    return float(np.std(dts) / med)


def dedupe_time_series(
    t: ArrayLike,
    *channels: ArrayLike,
) -> tuple[ArrayF, ...]:
    """Keep the first sample of each strictly-increasing timestamp."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if t.size == 0:
        raise ValueError("empty time series")
    keep = np.ones(t.shape[0], dtype=bool)
    keep[1:] = np.diff(t) > 1e-9
    outs: list[ArrayF] = [t[keep]]
    for ch in channels:
        arr = np.asarray(ch, dtype=np.float64)
        outs.append(arr[keep])
    return tuple(outs)


def needs_fixed_rate(
    t: ArrayLike,
    *,
    max_jitter_cv: float = 0.08,
    max_dup_frac: float = 0.01,
) -> bool:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if t.size < 3:
        return False
    dups = float(np.mean(np.diff(t) <= 1e-9))
    if dups > max_dup_frac:
        return True
    return timestamp_jitter_cv(t) > max_jitter_cv


def resample_packet(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    fs_hz: float,
    frame: SensorFrame | None = None,
) -> ImuPacket:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    if t.shape[0] < 2:
        raise ValueError("need >= 2 samples")
    t, gyro, accel = dedupe_time_series(t, gyro, accel)
    if t.shape[0] < 2:
        raise ValueError("need >= 2 unique timestamps")
    t0, t1 = float(t[0]), float(t[-1])
    n = max(2, int(np.floor((t1 - t0) * fs_hz)) + 1)
    tg = t0 + np.arange(n, dtype=np.float64) / fs_hz
    # Clamp grid end to last sample so we never extrapolate
    tg = tg[tg <= t1 + 0.5 / fs_hz]
    if tg.size < 2:
        tg = np.array([t0, t1], dtype=np.float64)
    g = np.column_stack([np.interp(tg, t, gyro[:, i]) for i in range(3)])
    a = np.column_stack([np.interp(tg, t, accel[:, i]) for i in range(3)])
    if frame is None:
        frame = SensorFrame(fs_hz=fs_hz)
    else:
        frame = SensorFrame(
            fs_hz=fs_hz,
            wrist=frame.wrist,
            handedness=frame.handedness,
            mount_extrinsic=frame.mount_extrinsic,
            device_id=frame.device_id,
            is_canonical=frame.is_canonical,
        )
    return ImuPacket(frame=frame, t=tg, gyro=g, accel=a)


def ensure_fixed_rate_packet(
    packet: ImuPacket,
    *,
    max_jitter_cv: float = 0.08,
    target_fs_hz: float | None = None,
) -> tuple[ImuPacket, bool]:
    """Resample when timestamps are irregular; otherwise return unchanged."""
    if not needs_fixed_rate(packet.t, max_jitter_cv=max_jitter_cv) and target_fs_hz is None:
        return packet, False
    t = np.asarray(packet.t, dtype=np.float64)
    dts = np.diff(t)
    dts = dts[dts > 0]
    med_fs = 1.0 / float(np.median(dts)) if dts.size else float(packet.frame.fs_hz)
    fs = float(target_fs_hz) if target_fs_hz is not None else float(np.clip(med_fs, 40.0, 800.0))
    # Prefer declared fs when close to median (stable contract)
    if target_fs_hz is None and abs(med_fs - packet.frame.fs_hz) / max(med_fs, 1.0) < 0.15:
        fs = float(packet.frame.fs_hz)
    out = resample_packet(packet.t, packet.gyro, packet.accel, fs, frame=packet.frame)
    return out, True
