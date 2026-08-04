"""PackedCapture V2 codec + WatchCapture JSON v1 compatibility."""

from __future__ import annotations

import json
import struct
import zlib

import numpy as np
import pytest

from golfmate_algo.devices.packed_capture_v2 import (
    FLAG_HAS_PREVIEW,
    FLAG_PAYLOAD_ZLIB,
    HEADER_BASE_SIZE,
    MAGIC,
    PREVIEW_POINTS,
    crc32_payload,
    decode_packed_capture_v2,
    encode_packed_capture_v2,
    is_packed_capture_v2,
    packed_from_v1_dict,
)
from golfmate_algo.devices.watch_capture import G0, load_watch_capture
from golfmate_algo.synth.analytic import planar_circular_swing


def _v1_payload(*, fs_motion=200.0, fs_accel=800.0, capture_mode="high_rate", preview=False):
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
    if preview:
        payload["preview"] = {
            "trajectory": np.zeros((PREVIEW_POINTS, 3), dtype=np.float64).tolist(),
            "confidence": 0.42,
            "quality": 0.40,
            "source": "on_device_preview",
        }
    return payload, swing


def test_packed_v2_roundtrip_uncompressed_and_zlib():
    payload, _ = _v1_payload()
    for compress in (False, True):
        wire = encode_packed_capture_v2(payload, compress=compress)
        assert is_packed_capture_v2(wire)
        assert wire[:4] == MAGIC
        decoded = decode_packed_capture_v2(wire)
        assert decoded.capture_mode == "high_rate"
        assert decoded.zlib_payload is compress
        assert decoded.accel_t.size == len(payload["accelerometer800Hz"])
        assert decoded.motion_t.size == len(payload["deviceMotion200Hz"])
        # Timestamp reconstruction within 1.5 µs after delta quantization.
        src_a = np.asarray([r["timestamp"] for r in payload["accelerometer800Hz"]])
        assert np.max(np.abs(decoded.accel_t - src_a)) < 1.5e-6
        src_g = np.asarray(
            [
                [
                    r["rotationRate"]["x"],
                    r["rotationRate"]["y"],
                    r["rotationRate"]["z"],
                ]
                for r in payload["deviceMotion200Hz"]
            ]
        )
        assert np.allclose(decoded.motion_gyro, src_g, rtol=0, atol=1e-6)


def test_packed_v2_crc_detects_corruption():
    payload, _ = _v1_payload()
    wire = bytearray(encode_packed_capture_v2(payload, compress=False))
    # Flip a payload byte after the header.
    wire[HEADER_BASE_SIZE + 20] ^= 0x5A
    with pytest.raises(ValueError, match="CRC"):
        decode_packed_capture_v2(bytes(wire))


def test_packed_v2_rejects_bad_magic_truncated_and_bad_zlib():
    with pytest.raises(ValueError, match="magic|truncated"):
        decode_packed_capture_v2(b"XXXX" + b"\x00" * 200)
    with pytest.raises(ValueError, match="truncated"):
        decode_packed_capture_v2(MAGIC + b"\x02\x00")

    payload, _ = _v1_payload()
    wire = bytearray(encode_packed_capture_v2(payload, compress=True))
    # Corrupt zlib stream but keep header CRC pointing at original uncompressed.
    wire[-5] ^= 0xFF
    with pytest.raises(ValueError, match="zlib"):
        decode_packed_capture_v2(bytes(wire))


def test_packed_v2_preview_block_roundtrip():
    payload, _ = _v1_payload(preview=True)
    wire = encode_packed_capture_v2(payload, compress=False)
    flags = struct.unpack_from("<I", wire, 8)[0]
    assert flags & FLAG_HAS_PREVIEW
    assert not (flags & FLAG_PAYLOAD_ZLIB)
    decoded = decode_packed_capture_v2(wire)
    assert decoded.preview is not None
    assert decoded.preview.confidence == pytest.approx(0.42)
    assert decoded.preview.xyz.shape == (PREVIEW_POINTS, 3)
    as_v1 = decoded.to_v1_dict()
    assert "preview" in as_v1
    assert as_v1["preview"]["confidence"] == pytest.approx(0.42)


def test_load_watch_capture_accepts_packed_v2_and_json_v1(tmp_path):
    payload, swing = _v1_payload(fs_motion=100.0, fs_accel=100.0, capture_mode="compat")
    json_path = tmp_path / "v1.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    packed_path = tmp_path / "v2.bin"
    packed_path.write_bytes(encode_packed_capture_v2(payload, compress=True))

    cap_json = load_watch_capture(json_path)
    cap_bin = load_watch_capture(packed_path)
    assert cap_json.capture_mode == cap_bin.capture_mode == "compat"
    assert cap_json.packet.frame.fs_hz == pytest.approx(cap_bin.packet.frame.fs_hz, rel=1e-6)
    assert np.allclose(cap_json.packet.gyro, cap_bin.packet.gyro, rtol=0, atol=1e-5)
    assert np.allclose(cap_json.accel_g_800, cap_bin.accel_g_800, rtol=0, atol=1e-5)
    # Pipeline still runs.
    report = cap_bin.analyze(compare_to_ideal=False)
    assert report.phases.impact_idx > report.phases.top_idx
    assert abs(float(cap_bin.packet.t[report.phases.impact_idx]) - float(swing.packet.t[swing.phases_true.impact_idx])) <= 0.05


def test_packed_crc_matches_zlib_polynomial():
    payload, _ = _v1_payload()
    packed = packed_from_v1_dict(payload)
    wire = encode_packed_capture_v2(packed, compress=False)
    nbytes = struct.unpack_from("<I", wire, 128)[0]
    stored_crc = struct.unpack_from("<I", wire, 132)[0]
    uncompressed = wire[HEADER_BASE_SIZE:]
    assert len(uncompressed) == nbytes
    assert stored_crc == (zlib.crc32(uncompressed) & 0xFFFFFFFF)
    assert stored_crc == crc32_payload(uncompressed)
