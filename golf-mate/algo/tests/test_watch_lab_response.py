"""Watch lab analysis response: finalTrajectory + preview/final metadata."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from golfmate_algo.devices.packed_capture_v2 import PREVIEW_POINTS, encode_packed_capture_v2
from golfmate_algo.devices.watch_capture import G0
from golfmate_algo.export.edge_trajectory_contract import TRAJECTORY_POINTS
from golfmate_algo.synth.analytic import planar_circular_swing

# Import from scripts path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from watch_lab_server import analyze_bytes, analyze_payload  # noqa: E402


def _payload(*, capture_mode="high_rate", fs_motion=200.0, fs_accel=800.0, preview=False):
    swing = planar_circular_swing(fs_hz=fs_motion, impact_shock_g=4.0)
    t_motion = swing.packet.t
    t_accel = np.arange(int(round(t_motion[-1] * fs_accel)) + 1) / fs_accel
    accel_g = np.column_stack(
        [
            np.interp(t_accel, t_motion, swing.packet.accel[:, axis] / G0)
            for axis in range(3)
        ]
    )
    payload = {
        "schemaVersion": "golfmate-watch-capture-v1",
        "sessionID": "E9DA174A-E1E0-4BA8-8AD0-EC54B84D7D07",
        "startedAtUnix": 1000.0,
        "endedAtUnix": 1000.0 + float(t_motion[-1]),
        "handedness": "right",
        "wrist": "lead",
        "mountExtrinsicWXYZ": [1, 0, 0, 0],
        "captureMode": capture_mode,
        "device": {
            "model": "Watch7,5",
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
    if preview:
        payload["preview"] = {
            "trajectory": (np.linspace(0, 1, PREVIEW_POINTS).reshape(-1, 1) * np.array([0.1, 0.0, 0.2])).tolist(),
            "confidence": 0.33,
            "quality": 0.30,
            "source": "on_device_preview",
        }
    return payload


def test_analyze_payload_includes_final_trajectory_and_mode():
    result = analyze_payload(_payload(preview=True))
    assert result["ok"] is True
    assert result["captureMode"] == "high_rate"
    assert len(result["finalTrajectory"]) == TRAJECTORY_POINTS
    assert len(result["finalTrajectory"][0]) == 3
    assert 0.05 <= result["trajectoryConfidence"] <= 0.95
    assert result["trajectoryQuality"]["pointCount"] == TRAJECTORY_POINTS
    assert result["trajectoryQuality"]["source"] == "python_analyze_swing"
    assert result["final"]["trajectory"] == result["finalTrajectory"]
    assert result["final"]["confidence"] == result["trajectoryConfidence"]
    assert result["preview"] is not None
    assert result["preview"]["confidence"] == pytest.approx(0.33)
    assert result["preview"]["pointCount"] == PREVIEW_POINTS
    # Preview and final are distinct sources.
    assert result["preview"]["source"] != result["final"]["source"]
    assert "phases" in result and "features" in result
    commercial = result["commercialReport"]
    assert commercial["version"] == "commercial-swing-report-v2"
    assert commercial["truth"]
    assert all("kind" in metric and "validity" in metric for metric in commercial["truth"])
    assert result["meta"]["truth_quality"] is not None
    assert result["meta"]["feature_quality"] is not None
    # iOS JSONDecoder requires standards-compliant JSON; abstained inferred
    # values must be null, never NaN/Infinity.
    json.dumps(result, allow_nan=False)


def test_analyze_bytes_packed_v2():
    payload = _payload(capture_mode="compat", fs_motion=100.0, fs_accel=100.0, preview=True)
    wire = encode_packed_capture_v2(payload, compress=False)
    result = analyze_bytes(wire)
    assert result["ok"] is True
    assert result["captureMode"] == "compat"
    assert len(result["finalTrajectory"]) == TRAJECTORY_POINTS
    assert result["preview"]["confidence"] == pytest.approx(0.33)


def test_analyze_payload_without_preview_sets_null_preview():
    result = analyze_payload(_payload(preview=False))
    assert result["preview"] is None
    assert result["final"] is not None
    assert len(result["finalTrajectory"]) == TRAJECTORY_POINTS
