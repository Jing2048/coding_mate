"""Apple Watch ``golfmate-watch-capture-v1`` adapter.

The Watch keeps native 800 Hz accelerometer and 200 Hz Device Motion streams.
This adapter aligns raw acceleration onto the 200 Hz AHRS grid without deleting
the high-rate sidecar, and exposes a sub-frame collision timestamp to the
pipeline via ``impact_hint_s``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from golfmate_algo.events.segmental import _impact_transient, detect_phases_segmental
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.types import (
    Handedness,
    ImuPacket,
    SensorFrame,
    SwingReport,
    WristSide,
)

SCHEMA_VERSION = "golfmate-watch-capture-v1"
G0 = 9.80665


@dataclass(frozen=True)
class WatchCapture:
    packet: ImuPacket
    accel_t_800: np.ndarray
    accel_g_800: np.ndarray
    metadata: dict[str, Any]

    def high_rate_impact_time_s(self) -> float | None:
        """Return collision timestamp from the native 800 Hz stream.

        Search starts near peak wrist rate after Top to reject backswing/release
        transients. Thresholding uses only the post-peak score so an early,
        stronger casting spike cannot suppress the actual strike.
        """
        if self.accel_t_800.size < 40 or self.packet.t.size < 20:
            return None
        fs_800 = _median_fs(self.accel_t_800)
        if fs_800 < 400.0:
            return None

        phases = detect_phases_segmental(
            self.packet.t, self.packet.gyro, self.packet.accel
        )
        peak_gyro_idx = int(np.argmax(np.linalg.norm(self.packet.gyro, axis=1)))
        peak_t = float(self.packet.t[peak_gyro_idx])
        top_t = float(self.packet.t[phases.top_idx])
        lo_t = max(top_t, peak_t - 0.02)
        hi_t = min(
            float(self.accel_t_800[-1]),
            float(self.packet.t[phases.finish_idx]) + 0.15,
        )

        score = _impact_transient(np.linalg.norm(self.accel_g_800, axis=1), fs_800)
        mask = (self.accel_t_800 >= lo_t) & (self.accel_t_800 <= hi_t)
        idxs = np.flatnonzero(mask)
        if idxs.size < 3:
            return None
        local = score[idxs]
        floor = float(np.median(score)) + 1e-12
        peak = float(np.max(local))
        if peak / floor < 4.0:
            return None
        threshold = max(4.0 * floor, 0.30 * peak)
        candidates = [
            int(idxs[j])
            for j in range(1, idxs.size - 1)
            if local[j] >= threshold
            and local[j] >= local[j - 1]
            and local[j] >= local[j + 1]
        ]
        if not candidates:
            return float(self.accel_t_800[int(idxs[int(np.argmax(local))])])
        best = max(candidates, key=lambda i: float(score[i]))
        return float(self.accel_t_800[best])

    def analyze(self, **kwargs: Any) -> SwingReport:
        """Run the unchanged precision pipeline with the 800 Hz impact hint."""
        return analyze_swing(
            self.packet,
            impact_hint_s=self.high_rate_impact_time_s(),
            **kwargs,
        )


def load_watch_capture(path: str | Path) -> WatchCapture:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported Watch schema: {payload.get('schemaVersion')!r}"
        )

    accel_rows = payload.get("accelerometer800Hz") or []
    motion_rows = payload.get("deviceMotion200Hz") or []
    if len(accel_rows) < 2 or len(motion_rows) < 2:
        raise ValueError("Watch capture requires both 800 Hz accel and 200 Hz motion")

    accel_t_abs = np.asarray([row["timestamp"] for row in accel_rows], dtype=np.float64)
    accel_g = np.asarray(
        [[row["x"], row["y"], row["z"]] for row in accel_rows], dtype=np.float64
    )
    motion_t_abs = np.asarray(
        [row["timestamp"] for row in motion_rows], dtype=np.float64
    )
    gyro = np.asarray(
        [
            [
                row["rotationRate"]["x"],
                row["rotationRate"]["y"],
                row["rotationRate"]["z"],
            ]
            for row in motion_rows
        ],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(accel_g)) or not np.all(np.isfinite(gyro)):
        raise ValueError("Watch capture contains non-finite sensor values")

    accel_t_abs, accel_g = _sort_dedupe(accel_t_abs, accel_g)
    motion_t_abs, gyro = _sort_dedupe(motion_t_abs, gyro)
    origin = min(float(accel_t_abs[0]), float(motion_t_abs[0]))
    accel_t = accel_t_abs - origin
    motion_t = motion_t_abs - origin

    # Native accelerometer is in g. Interpolate each axis to Device Motion time;
    # this is the only rate conversion and leaves accel_g_800 untouched.
    accel_200 = np.column_stack(
        [np.interp(motion_t, accel_t, accel_g[:, axis]) for axis in range(3)]
    ) * G0
    fs = _median_fs(motion_t)
    if not 120.0 <= fs <= 240.0:
        raise ValueError(f"unexpected Device Motion sample rate: {fs:.2f} Hz")

    handedness = Handedness(payload.get("handedness", "right"))
    wrist = WristSide(payload.get("wrist", "lead"))
    extrinsic = payload.get("mountExtrinsicWXYZ", [1.0, 0.0, 0.0, 0.0])
    if len(extrinsic) != 4:
        raise ValueError("mountExtrinsicWXYZ must have four values")
    device = payload.get("device") or {}
    packet = ImuPacket(
        frame=SensorFrame(
            fs_hz=fs,
            wrist=wrist,
            handedness=handedness,
            mount_extrinsic=tuple(float(x) for x in extrinsic),
            device_id=f"apple_watch/{device.get('model', 'unknown')}",
            is_canonical=False,
        ),
        t=motion_t,
        gyro=gyro,
        accel=accel_200,
    )
    return WatchCapture(
        packet=packet,
        accel_t_800=accel_t,
        accel_g_800=accel_g,
        metadata=payload,
    )


def _sort_dedupe(t: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(t, kind="stable")
    t_sorted = t[order]
    values_sorted = values[order]
    keep = np.concatenate(([True], np.diff(t_sorted) > 1e-9))
    t_out = t_sorted[keep]
    values_out = values_sorted[keep]
    if t_out.size < 2 or np.any(np.diff(t_out) <= 0):
        raise ValueError("sensor timestamps must be monotonic")
    return t_out, values_out


def _median_fs(t: np.ndarray) -> float:
    dt = float(np.median(np.diff(np.asarray(t, dtype=np.float64))))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("invalid Watch timestamps")
    return 1.0 / dt
