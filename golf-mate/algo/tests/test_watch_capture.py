from __future__ import annotations

import json

import numpy as np
import pytest

from golfmate_algo.devices.watch_capture import G0, load_watch_capture
from golfmate_algo.synth.analytic import planar_circular_swing


def _write_capture(tmp_path, *, fs_motion=200.0, fs_accel=800.0, capture_mode="high_rate"):
    swing = planar_circular_swing(fs_hz=fs_motion, impact_shock_g=4.0)
    t_motion = swing.packet.t
    t_accel = np.arange(int(round(t_motion[-1] * fs_accel)) + 1) / fs_accel
    accel_g = np.column_stack(
        [
            np.interp(t_accel, t_motion, swing.packet.accel[:, axis] / G0)
            for axis in range(3)
        ]
    )
    impact_t = float(t_motion[swing.phases_true.impact_idx])
    # Narrower shock for high-rate; wider for ~100 Hz so it still lands in samples.
    sigma = 0.0015 if fs_accel >= 400.0 else 0.008
    shock = 12.0 * np.exp(-0.5 * ((t_accel - impact_t) / sigma) ** 2)
    accel_g[:, 2] += shock

    payload = {
        "schemaVersion": "golfmate-watch-capture-v1",
        "sessionID": "E9DA174A-E1E0-4BA8-8AD0-EC54B84D7D07",
        "startedAt": "2026-08-03T00:00:00Z",
        "endedAt": "2026-08-03T00:00:04Z",
        "handedness": "right",
        "wrist": "lead",
        "mountExtrinsicWXYZ": [1, 0, 0, 0],
        "captureMode": capture_mode,
        "device": {
            "model": "Watch7,5" if capture_mode == "high_rate" else "Watch5,2",
            "systemVersion": "10.0",
            "accelerometerHz": fs_accel,
            "deviceMotionHz": fs_motion,
        },
        "accelerometer800Hz": [
            {
                "timestamp": float(1000.0 + t),
                "x": float(a[0]),
                "y": float(a[1]),
                "z": float(a[2]),
            }
            for t, a in zip(t_accel, accel_g)
        ],
        "deviceMotion200Hz": [
            {
                "timestamp": float(1000.0 + t),
                "rotationRate": {
                    "x": float(g[0]),
                    "y": float(g[1]),
                    "z": float(g[2]),
                },
                "gravity": {"x": 0.0, "y": 0.0, "z": -1.0},
                "userAcceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
                "attitudeWXYZ": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0},
            }
            for t, g in zip(t_motion, swing.packet.gyro)
        ],
    }
    path = tmp_path / f"watch_{capture_mode}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, swing, impact_t


def test_watch_capture_preserves_dual_rates_and_units(tmp_path):
    path, swing, _ = _write_capture(tmp_path)
    capture = load_watch_capture(path)
    assert capture.capture_mode == "high_rate"
    assert capture.accel_t_800.size > capture.packet.t.size * 3.9
    assert capture.packet.frame.fs_hz == pytest.approx(200.0, rel=1e-6)
    assert capture.packet.frame.device_id == "apple_watch/Watch7,5"
    # Device adapter converts native g to the pipeline m/s² contract.
    quiet = slice(0, 20)
    assert np.median(np.linalg.norm(capture.packet.accel[quiet], axis=1)) == pytest.approx(
        np.median(np.linalg.norm(swing.packet.accel[quiet], axis=1)),
        rel=0.02,
    )


def test_native_800hz_impact_hint_drives_full_pipeline(tmp_path):
    path, _, impact_t = _write_capture(tmp_path)
    capture = load_watch_capture(path)
    hint = capture.high_rate_impact_time_s()
    assert hint is not None
    assert abs(hint - impact_t) <= 0.0025

    report = capture.analyze(compare_to_ideal=False)
    detected_t = float(capture.packet.t[report.phases.impact_idx])
    assert abs(detected_t - impact_t) <= 0.0051
    assert report.meta["impact_mode"] == "collision"
    assert report.meta["impact_method"] == "high_rate_impact_hint"


def test_series5_compat_100hz_runs_full_pipeline_without_high_rate_hint(tmp_path):
    path, _, impact_t = _write_capture(
        tmp_path, fs_motion=100.0, fs_accel=100.0, capture_mode="compat"
    )
    capture = load_watch_capture(path)
    assert capture.capture_mode == "compat"
    assert capture.packet.frame.fs_hz == pytest.approx(100.0, rel=1e-6)
    assert capture.packet.frame.device_id == "apple_watch/Watch5,2"
    assert capture.high_rate_impact_time_s() is None

    report = capture.analyze(compare_to_ideal=False)
    detected_t = float(capture.packet.t[report.phases.impact_idx])
    # Compat trades sub-frame impact precision for hardware reach.
    assert abs(detected_t - impact_t) <= 0.04
    assert report.meta.get("impact_method") != "high_rate_impact_hint"


def test_watch_capture_rejects_incomplete_streams(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "golfmate-watch-capture-v1",
                "accelerometer800Hz": [],
                "deviceMotion200Hz": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires both"):
        load_watch_capture(path)
