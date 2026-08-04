"""PackedCapture V2 binary codec (``golfmate-watch-capture-v2``).

See ``PACKED_CAPTURE_V2.md`` for the cross-platform wire format.
This module is the Python reference encoder/decoder for Swift parity tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import uuid
import zlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

MAGIC = b"GMPC"
VERSION = 2
HEADER_BASE_SIZE = 136
PREVIEW_BLOCK_SIZE = 780
PREVIEW_POINTS = 64
SCHEMA_VERSION_V2 = "golfmate-watch-capture-v2"

FLAG_PAYLOAD_ZLIB = 1 << 0
FLAG_HAS_PREVIEW = 1 << 1

_CAPTURE_MODE = {"compat": 0, "high_rate": 1}
_CAPTURE_MODE_INV = {v: k for k, v in _CAPTURE_MODE.items()}
_HANDEDNESS = {"right": 0, "left": 1}
_HANDEDNESS_INV = {v: k for k, v in _HANDEDNESS.items()}
_WRIST = {"lead": 0, "trail": 1}
_WRIST_INV = {v: k for k, v in _WRIST.items()}

_HEADER_STRUCT = struct.Struct("<4sHHIBBBBffII16sdd4f32s16sII")


@dataclass(frozen=True)
class PackedPreview:
    confidence: float
    quality: float
    xyz: NDArray[np.float64]  # (64, 3)


@dataclass(frozen=True)
class PackedCaptureV2:
    """Decoded packed capture before WatchCapture adaptation."""

    capture_mode: str
    handedness: str
    wrist: str
    accelerometer_hz: float
    device_motion_hz: float
    session_id: str
    started_at_unix: float
    ended_at_unix: float
    mount_extrinsic_wxyz: tuple[float, float, float, float]
    device_model: str
    system_version: str
    accel_t: NDArray[np.float64]
    accel_g: NDArray[np.float64]
    motion_t: NDArray[np.float64]
    motion_gyro: NDArray[np.float64]
    motion_gravity: NDArray[np.float64]
    motion_user_accel: NDArray[np.float64]
    motion_attitude_wxyz: NDArray[np.float64]
    preview: PackedPreview | None = None
    zlib_payload: bool = False

    def to_v1_dict(self) -> dict[str, Any]:
        """Materialize a v1-compatible JSON object (field names preserved)."""
        out: dict[str, Any] = {
            "schemaVersion": "golfmate-watch-capture-v1",
            "packedSchemaVersion": SCHEMA_VERSION_V2,
            "sessionID": self.session_id,
            "startedAtUnix": float(self.started_at_unix),
            "endedAtUnix": float(self.ended_at_unix),
            "handedness": self.handedness,
            "wrist": self.wrist,
            "mountExtrinsicWXYZ": list(self.mount_extrinsic_wxyz),
            "captureMode": self.capture_mode,
            "device": {
                "model": self.device_model,
                "systemVersion": self.system_version,
                "accelerometerHz": float(self.accelerometer_hz),
                "deviceMotionHz": float(self.device_motion_hz),
            },
            "accelerometer800Hz": [
                {
                    "timestamp": float(t),
                    "x": float(a[0]),
                    "y": float(a[1]),
                    "z": float(a[2]),
                }
                for t, a in zip(self.accel_t, self.accel_g)
            ],
            "deviceMotion200Hz": [
                {
                    "timestamp": float(t),
                    "rotationRate": {
                        "x": float(g[0]),
                        "y": float(g[1]),
                        "z": float(g[2]),
                    },
                    "gravity": {
                        "x": float(gv[0]),
                        "y": float(gv[1]),
                        "z": float(gv[2]),
                    },
                    "userAcceleration": {
                        "x": float(ua[0]),
                        "y": float(ua[1]),
                        "z": float(ua[2]),
                    },
                    "attitudeWXYZ": {
                        "w": float(q[0]),
                        "x": float(q[1]),
                        "y": float(q[2]),
                        "z": float(q[3]),
                    },
                }
                for t, g, gv, ua, q in zip(
                    self.motion_t,
                    self.motion_gyro,
                    self.motion_gravity,
                    self.motion_user_accel,
                    self.motion_attitude_wxyz,
                )
            ],
        }
        if self.preview is not None:
            out["preview"] = {
                "trajectory": self.preview.xyz.astype(np.float64).tolist(),
                "confidence": float(self.preview.confidence),
                "quality": float(self.preview.quality),
                "pointCount": PREVIEW_POINTS,
                "source": "on_device_preview",
            }
        return out


def is_packed_capture_v2(data: bytes | bytearray | memoryview) -> bool:
    raw = bytes(data[:8]) if len(data) >= 8 else bytes(data)
    if len(raw) < 8:
        return False
    return raw[:4] == MAGIC and struct.unpack_from("<H", raw, 4)[0] == VERSION


def expected_payload_nbytes(accel_count: int, motion_count: int) -> int:
    return 16 + 16 * int(accel_count) + 56 * int(motion_count)


def crc32_payload(uncompressed: bytes) -> int:
    return zlib.crc32(uncompressed) & 0xFFFFFFFF


def _nul_pad(text: str, size: int) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) > size:
        raw = raw[:size]
    return raw + b"\x00" * (size - len(raw))


def _nul_strip(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _timestamps_to_dt_us(t: NDArray[np.float64]) -> tuple[float, NDArray[np.uint32]]:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if t.size < 2:
        raise ValueError("need >= 2 timestamps")
    if not np.all(np.isfinite(t)):
        raise ValueError("non-finite timestamps")
    if np.any(np.diff(t) <= 0):
        raise ValueError("timestamps must be strictly increasing")
    t0 = float(t[0])
    dt_s = np.diff(t)
    dt_us = np.zeros(t.size, dtype=np.uint32)
    # Round to nearest microsecond; reject pathological gaps.
    rounded = np.rint(dt_s * 1_000_000.0)
    if np.any(rounded <= 0) or np.any(rounded > np.iinfo(np.uint32).max):
        raise ValueError("timestamp deltas out of uint32 microsecond range")
    dt_us[1:] = rounded.astype(np.uint32)
    return t0, dt_us


def _dt_us_to_timestamps(t0: float, dt_us: NDArray[np.uint32]) -> NDArray[np.float64]:
    dt_us = np.asarray(dt_us, dtype=np.uint32).reshape(-1)
    if dt_us.size < 2:
        raise ValueError("need >= 2 samples")
    if int(dt_us[0]) != 0:
        raise ValueError("first delta timestamp must be 0")
    if np.any(dt_us[1:] == 0):
        raise ValueError("zero inter-sample delta")
    cum = np.cumsum(dt_us.astype(np.float64)) * 1e-6
    return float(t0) + cum


def _build_uncompressed_payload(
    *,
    accel_t: NDArray[np.float64],
    accel_g: NDArray[np.float64],
    motion_t: NDArray[np.float64],
    motion_gyro: NDArray[np.float64],
    motion_gravity: NDArray[np.float64],
    motion_user_accel: NDArray[np.float64],
    motion_attitude_wxyz: NDArray[np.float64],
) -> bytes:
    accel_t0, accel_dt = _timestamps_to_dt_us(accel_t)
    motion_t0, motion_dt = _timestamps_to_dt_us(motion_t)
    accel_g = np.asarray(accel_g, dtype=np.float32).reshape(-1, 3)
    motion_gyro = np.asarray(motion_gyro, dtype=np.float32).reshape(-1, 3)
    motion_gravity = np.asarray(motion_gravity, dtype=np.float32).reshape(-1, 3)
    motion_user_accel = np.asarray(motion_user_accel, dtype=np.float32).reshape(-1, 3)
    motion_attitude_wxyz = np.asarray(motion_attitude_wxyz, dtype=np.float32).reshape(
        -1, 4
    )
    n_a, n_m = accel_g.shape[0], motion_gyro.shape[0]
    if accel_dt.size != n_a or motion_dt.size != n_m:
        raise ValueError("timestamp/channel length mismatch")
    if motion_gravity.shape[0] != n_m or motion_user_accel.shape[0] != n_m:
        raise ValueError("motion channel length mismatch")
    if motion_attitude_wxyz.shape[0] != n_m:
        raise ValueError("attitude length mismatch")
    for name, arr in (
        ("accel", accel_g),
        ("gyro", motion_gyro),
        ("gravity", motion_gravity),
        ("user_accel", motion_user_accel),
        ("attitude", motion_attitude_wxyz),
    ):
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"non-finite {name} channels")

    parts = [
        struct.pack("<dd", accel_t0, motion_t0),
        accel_dt.astype("<u4", copy=False).tobytes(),
        accel_g.astype("<f4", copy=False).reshape(-1).tobytes(),
        motion_dt.astype("<u4", copy=False).tobytes(),
        motion_gyro.astype("<f4", copy=False).reshape(-1).tobytes(),
        motion_gravity.astype("<f4", copy=False).reshape(-1).tobytes(),
        motion_user_accel.astype("<f4", copy=False).reshape(-1).tobytes(),
        motion_attitude_wxyz.astype("<f4", copy=False).reshape(-1).tobytes(),
    ]
    raw = b"".join(parts)
    expected = expected_payload_nbytes(n_a, n_m)
    if len(raw) != expected:
        raise RuntimeError(f"payload size {len(raw)} != expected {expected}")
    return raw


def encode_packed_capture_v2(
    capture: PackedCaptureV2 | Mapping[str, Any],
    *,
    compress: bool = False,
) -> bytes:
    """Encode a PackedCaptureV2 or v1-like dict to wire bytes."""
    if isinstance(capture, Mapping):
        packed = packed_from_v1_dict(capture)
    else:
        packed = capture

    uncompressed = _build_uncompressed_payload(
        accel_t=packed.accel_t,
        accel_g=packed.accel_g,
        motion_t=packed.motion_t,
        motion_gyro=packed.motion_gyro,
        motion_gravity=packed.motion_gravity,
        motion_user_accel=packed.motion_user_accel,
        motion_attitude_wxyz=packed.motion_attitude_wxyz,
    )
    payload = zlib.compress(uncompressed, level=6) if compress else uncompressed
    flags = FLAG_PAYLOAD_ZLIB if compress else 0
    header_size = HEADER_BASE_SIZE
    preview_bytes = b""
    if packed.preview is not None:
        flags |= FLAG_HAS_PREVIEW
        xyz = np.asarray(packed.preview.xyz, dtype=np.float32).reshape(PREVIEW_POINTS, 3)
        preview_bytes = (
            struct.pack(
                "<ffHH",
                float(packed.preview.confidence),
                float(packed.preview.quality),
                PREVIEW_POINTS,
                0,
            )
            + xyz.astype("<f4", copy=False).reshape(-1).tobytes()
        )
        if len(preview_bytes) != PREVIEW_BLOCK_SIZE:
            raise RuntimeError("preview block size mismatch")
        header_size = HEADER_BASE_SIZE + PREVIEW_BLOCK_SIZE

    try:
        session_bytes = uuid.UUID(packed.session_id).bytes
    except ValueError as exc:
        raise ValueError(f"invalid session_id UUID: {packed.session_id!r}") from exc

    header = _HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        header_size,
        flags,
        _CAPTURE_MODE[packed.capture_mode],
        _HANDEDNESS[packed.handedness],
        _WRIST[packed.wrist],
        0,
        float(packed.accelerometer_hz),
        float(packed.device_motion_hz),
        int(packed.accel_t.size),
        int(packed.motion_t.size),
        session_bytes,
        float(packed.started_at_unix),
        float(packed.ended_at_unix),
        float(packed.mount_extrinsic_wxyz[0]),
        float(packed.mount_extrinsic_wxyz[1]),
        float(packed.mount_extrinsic_wxyz[2]),
        float(packed.mount_extrinsic_wxyz[3]),
        _nul_pad(packed.device_model, 32),
        _nul_pad(packed.system_version, 16),
        len(uncompressed),
        crc32_payload(uncompressed),
    )
    if len(header) != HEADER_BASE_SIZE:
        raise RuntimeError(f"header size {len(header)} != {HEADER_BASE_SIZE}")
    return header + preview_bytes + payload


def decode_packed_capture_v2(data: bytes | bytearray | memoryview) -> PackedCaptureV2:
    raw = bytes(data)
    if len(raw) < HEADER_BASE_SIZE:
        raise ValueError("packed capture truncated (header)")
    (
        magic,
        version,
        header_size,
        flags,
        mode_u8,
        hand_u8,
        wrist_u8,
        _reserved0,
        accel_hz,
        motion_hz,
        accel_count,
        motion_count,
        session_bytes,
        started,
        ended,
        mw,
        mx,
        my,
        mz,
        model_raw,
        sys_raw,
        payload_nbytes,
        payload_crc,
    ) = _HEADER_STRUCT.unpack_from(raw, 0)

    if magic != MAGIC:
        raise ValueError(f"bad packed magic: {magic!r}")
    if version != VERSION:
        raise ValueError(f"unsupported packed version: {version}")
    if header_size < HEADER_BASE_SIZE or header_size > len(raw):
        raise ValueError(f"invalid header_size: {header_size}")
    if accel_count < 2 or motion_count < 2:
        raise ValueError("packed capture requires both accel and Device Motion streams")
    if mode_u8 not in _CAPTURE_MODE_INV:
        raise ValueError(f"unsupported capture_mode code: {mode_u8}")
    if hand_u8 not in _HANDEDNESS_INV:
        raise ValueError(f"unsupported handedness code: {hand_u8}")
    if wrist_u8 not in _WRIST_INV:
        raise ValueError(f"unsupported wrist code: {wrist_u8}")

    has_preview = bool(flags & FLAG_HAS_PREVIEW)
    expected_header = HEADER_BASE_SIZE + (PREVIEW_BLOCK_SIZE if has_preview else 0)
    if header_size != expected_header:
        raise ValueError(
            f"header_size {header_size} does not match flags (expected {expected_header})"
        )

    preview: PackedPreview | None = None
    if has_preview:
        off = HEADER_BASE_SIZE
        conf, qual, n_pts, _res = struct.unpack_from("<ffHH", raw, off)
        off += 8
        if int(n_pts) != PREVIEW_POINTS:
            raise ValueError(f"preview_point_count must be {PREVIEW_POINTS}, got {n_pts}")
        xyz = np.frombuffer(raw, dtype="<f4", count=PREVIEW_POINTS * 3, offset=off).reshape(
            PREVIEW_POINTS, 3
        ).astype(np.float64)
        if not np.all(np.isfinite(xyz)):
            raise ValueError("non-finite preview trajectory")
        preview = PackedPreview(
            confidence=float(conf), quality=float(qual), xyz=xyz.copy()
        )

    payload_wire = raw[header_size:]
    if flags & FLAG_PAYLOAD_ZLIB:
        try:
            uncompressed = zlib.decompress(payload_wire)
        except zlib.error as exc:
            raise ValueError(f"zlib decompress failed: {exc}") from exc
    else:
        uncompressed = payload_wire

    if len(uncompressed) != int(payload_nbytes):
        raise ValueError(
            f"payload size mismatch: got {len(uncompressed)}, header says {payload_nbytes}"
        )
    expected = expected_payload_nbytes(accel_count, motion_count)
    if len(uncompressed) != expected:
        raise ValueError(
            f"payload size {len(uncompressed)} != layout expectation {expected}"
        )
    got_crc = crc32_payload(uncompressed)
    if got_crc != int(payload_crc):
        raise ValueError(
            f"payload CRC mismatch: got 0x{got_crc:08x}, expected 0x{payload_crc:08x}"
        )

    pos = 0
    accel_t0, motion_t0 = struct.unpack_from("<dd", uncompressed, pos)
    pos += 16
    accel_dt = np.frombuffer(
        uncompressed, dtype="<u4", count=accel_count, offset=pos
    ).copy()
    pos += 4 * accel_count
    accel_g = (
        np.frombuffer(uncompressed, dtype="<f4", count=accel_count * 3, offset=pos)
        .reshape(accel_count, 3)
        .astype(np.float64)
    )
    pos += 12 * accel_count
    motion_dt = np.frombuffer(
        uncompressed, dtype="<u4", count=motion_count, offset=pos
    ).copy()
    pos += 4 * motion_count
    motion_gyro = (
        np.frombuffer(uncompressed, dtype="<f4", count=motion_count * 3, offset=pos)
        .reshape(motion_count, 3)
        .astype(np.float64)
    )
    pos += 12 * motion_count
    motion_gravity = (
        np.frombuffer(uncompressed, dtype="<f4", count=motion_count * 3, offset=pos)
        .reshape(motion_count, 3)
        .astype(np.float64)
    )
    pos += 12 * motion_count
    motion_user_accel = (
        np.frombuffer(uncompressed, dtype="<f4", count=motion_count * 3, offset=pos)
        .reshape(motion_count, 3)
        .astype(np.float64)
    )
    pos += 12 * motion_count
    motion_attitude = (
        np.frombuffer(uncompressed, dtype="<f4", count=motion_count * 4, offset=pos)
        .reshape(motion_count, 4)
        .astype(np.float64)
    )
    pos += 16 * motion_count
    if pos != len(uncompressed):
        raise ValueError("payload trailing bytes")

    for name, arr in (
        ("accel", accel_g),
        ("gyro", motion_gyro),
        ("gravity", motion_gravity),
        ("user_accel", motion_user_accel),
        ("attitude", motion_attitude),
    ):
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"non-finite {name} channels")

    accel_t = _dt_us_to_timestamps(accel_t0, accel_dt)
    motion_t = _dt_us_to_timestamps(motion_t0, motion_dt)

    return PackedCaptureV2(
        capture_mode=_CAPTURE_MODE_INV[mode_u8],
        handedness=_HANDEDNESS_INV[hand_u8],
        wrist=_WRIST_INV[wrist_u8],
        accelerometer_hz=float(accel_hz),
        device_motion_hz=float(motion_hz),
        session_id=str(uuid.UUID(bytes=session_bytes)),
        started_at_unix=float(started),
        ended_at_unix=float(ended),
        mount_extrinsic_wxyz=(float(mw), float(mx), float(my), float(mz)),
        device_model=_nul_strip(model_raw),
        system_version=_nul_strip(sys_raw),
        accel_t=accel_t,
        accel_g=accel_g,
        motion_t=motion_t,
        motion_gyro=motion_gyro,
        motion_gravity=motion_gravity,
        motion_user_accel=motion_user_accel,
        motion_attitude_wxyz=motion_attitude,
        preview=preview,
        zlib_payload=bool(flags & FLAG_PAYLOAD_ZLIB),
    )


def packed_from_v1_dict(payload: Mapping[str, Any]) -> PackedCaptureV2:
    """Build PackedCaptureV2 from a v1 JSON-compatible dict."""
    accel_rows = payload.get("accelerometer800Hz") or []
    motion_rows = payload.get("deviceMotion200Hz") or []
    if len(accel_rows) < 2 or len(motion_rows) < 2:
        raise ValueError("Watch capture requires both accel and Device Motion streams")

    accel_t = np.asarray([row["timestamp"] for row in accel_rows], dtype=np.float64)
    accel_g = np.asarray(
        [[row["x"], row["y"], row["z"]] for row in accel_rows], dtype=np.float64
    )
    motion_t = np.asarray([row["timestamp"] for row in motion_rows], dtype=np.float64)
    motion_gyro = np.asarray(
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
    motion_gravity = np.asarray(
        [
            [
                row.get("gravity", {}).get("x", 0.0),
                row.get("gravity", {}).get("y", 0.0),
                row.get("gravity", {}).get("z", -1.0),
            ]
            for row in motion_rows
        ],
        dtype=np.float64,
    )
    motion_user = np.asarray(
        [
            [
                row.get("userAcceleration", {}).get("x", 0.0),
                row.get("userAcceleration", {}).get("y", 0.0),
                row.get("userAcceleration", {}).get("z", 0.0),
            ]
            for row in motion_rows
        ],
        dtype=np.float64,
    )
    motion_att = np.asarray(
        [
            [
                row.get("attitudeWXYZ", {}).get("w", 1.0),
                row.get("attitudeWXYZ", {}).get("x", 0.0),
                row.get("attitudeWXYZ", {}).get("y", 0.0),
                row.get("attitudeWXYZ", {}).get("z", 0.0),
            ]
            for row in motion_rows
        ],
        dtype=np.float64,
    )

    device = payload.get("device") or {}
    mode = payload.get("captureMode", "compat")
    if mode not in _CAPTURE_MODE:
        raise ValueError(f"unsupported captureMode: {mode!r}")
    handedness = str(payload.get("handedness", "right"))
    wrist = str(payload.get("wrist", "lead"))
    if handedness not in _HANDEDNESS or wrist not in _WRIST:
        raise ValueError("invalid handedness/wrist")
    extrinsic = payload.get("mountExtrinsicWXYZ", [1.0, 0.0, 0.0, 0.0])
    if len(extrinsic) != 4:
        raise ValueError("mountExtrinsicWXYZ must have four values")

    session = str(payload.get("sessionID") or payload.get("session_id") or uuid.uuid4())
    # Accept bare UUID strings; normalize via UUID parser.
    session = str(uuid.UUID(session)) if _looks_like_uuid(session) else str(uuid.uuid4())

    started = payload.get("startedAtUnix")
    ended = payload.get("endedAtUnix")
    if started is None:
        started = float(min(accel_t[0], motion_t[0]))
    if ended is None:
        ended = float(max(accel_t[-1], motion_t[-1]))

    preview = None
    prev = payload.get("preview")
    if isinstance(prev, Mapping) and "trajectory" in prev:
        xyz = np.asarray(prev["trajectory"], dtype=np.float64).reshape(PREVIEW_POINTS, 3)
        preview = PackedPreview(
            confidence=float(prev.get("confidence", 0.0)),
            quality=float(prev.get("quality", 0.0)),
            xyz=xyz,
        )

    accel_hz = float(device.get("accelerometerHz") or _median_fs(accel_t))
    motion_hz = float(device.get("deviceMotionHz") or _median_fs(motion_t))

    return PackedCaptureV2(
        capture_mode=str(mode),
        handedness=handedness,
        wrist=wrist,
        accelerometer_hz=accel_hz,
        device_motion_hz=motion_hz,
        session_id=session,
        started_at_unix=float(started),
        ended_at_unix=float(ended),
        mount_extrinsic_wxyz=tuple(float(x) for x in extrinsic),  # type: ignore[arg-type]
        device_model=str(device.get("model", "unknown")),
        system_version=str(device.get("systemVersion", "")),
        accel_t=accel_t,
        accel_g=accel_g,
        motion_t=motion_t,
        motion_gyro=motion_gyro,
        motion_gravity=motion_gravity,
        motion_user_accel=motion_user,
        motion_attitude_wxyz=motion_att,
        preview=preview,
    )


def load_packed_capture_v2(path: str | Path) -> PackedCaptureV2:
    return decode_packed_capture_v2(Path(path).read_bytes())


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _median_fs(t: NDArray[np.float64]) -> float:
    dt = float(np.median(np.diff(np.asarray(t, dtype=np.float64))))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("invalid timestamps")
    return 1.0 / dt
