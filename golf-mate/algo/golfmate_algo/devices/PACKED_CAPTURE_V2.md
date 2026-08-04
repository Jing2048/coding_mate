# PackedCapture V2 (`golfmate-watch-capture-v2`)

Compact binary sibling of the JSON `golfmate-watch-capture-v1` schema.
Designed for Watch → iPhone `WCSession.transferFile` and a matching Swift encoder.

Endianness: **little-endian** throughout.  
Checksum: **CRC-32/ISO-HDLC** (`zlib.crc32` / Apple `CRC32`) of the **uncompressed** payload.  
Compression: optional **zlib** (raw DEFLATE wrapper, `zlib.compress` / `Compression.zlib`). Uncompressed payload is valid and preferred when transfer size is acceptable.

## File layout

```text
[Header][optional PreviewBlock][Payload bytes] 
```

`header_size` is the byte offset from file start to the payload. Payload may be zlib-compressed when `flags & 0x1`.

## Header (136 bytes fixed base)

| Offset | Size | Type | Field |
|-------:|-----:|------|-------|
| 0 | 4 | bytes | `magic` = `GMPC` (`0x47 0x4D 0x50 0x43`) |
| 4 | 2 | u16 | `version` = `2` |
| 6 | 2 | u16 | `header_size` (offset of payload; ≥ 136) |
| 8 | 4 | u32 | `flags` (see below) |
| 12 | 1 | u8 | `capture_mode` — `0=compat`, `1=high_rate` |
| 13 | 1 | u8 | `handedness` — `0=right`, `1=left` |
| 14 | 1 | u8 | `wrist` — `0=lead`, `1=trail` |
| 15 | 1 | u8 | `reserved0` = 0 |
| 16 | 4 | f32 | `accelerometer_hz` (measured) |
| 20 | 4 | f32 | `device_motion_hz` (measured) |
| 24 | 4 | u32 | `accel_count` (≥ 2) |
| 28 | 4 | u32 | `motion_count` (≥ 2) |
| 32 | 16 | bytes | `session_id` UUID (RFC 4122 wire order) |
| 48 | 8 | f64 | `started_at_unix` seconds |
| 56 | 8 | f64 | `ended_at_unix` seconds |
| 64 | 16 | f32×4 | `mount_extrinsic_wxyz` |
| 80 | 32 | bytes | `device_model` UTF-8, NUL-padded |
| 112 | 16 | bytes | `system_version` UTF-8, NUL-padded |
| 128 | 4 | u32 | `payload_uncompressed_nbytes` |
| 132 | 4 | u32 | `payload_crc32` (of uncompressed payload) |

### Flags

| Bit | Name | Meaning |
|----:|------|---------|
| 0 | `PAYLOAD_ZLIB` | Payload bytes are `zlib.compress(uncompressed)` |
| 1 | `HAS_PREVIEW` | `PreviewBlock` follows the 136-byte base header |

## Optional PreviewBlock (780 bytes)

Present iff `HAS_PREVIEW`. Layout:

| Size | Type | Field |
|-----:|------|-------|
| 4 | f32 | `preview_confidence` (0..1) |
| 4 | f32 | `preview_quality` (0..1) |
| 2 | u16 | `preview_point_count` (must be 64) |
| 2 | u16 | `reserved1` = 0 |
| 768 | f32×192 | `preview_xyz` row-major 64×3 meters (address-relative) |

When present, `header_size` = 136 + 780 = 916.

## Uncompressed payload

All arrays are contiguous, tightly packed, little-endian.

| Section | Type | Count / shape | Units / notes |
|---------|------|---------------|---------------|
| `accel_t0` | f64 | 1 | Absolute device-clock seconds of first accel sample |
| `motion_t0` | f64 | 1 | Absolute device-clock seconds of first motion sample |
| `accel_dt_us` | u32 | `accel_count` | Inter-sample Δt in µs; index 0 must be 0 |
| `accel_xyz` | f32 | `accel_count × 3` | Native accelerometer **g** |
| `motion_dt_us` | u32 | `motion_count` | Inter-sample Δt in µs; index 0 must be 0 |
| `motion_gyro_xyz` | f32 | `motion_count × 3` | Rotation rate **rad/s** |
| `motion_gravity_xyz` | f32 | `motion_count × 3` | Device Motion gravity (g) |
| `motion_user_accel_xyz` | f32 | `motion_count × 3` | User acceleration (g) |
| `motion_attitude_wxyz` | f32 | `motion_count × 4` | Attitude quaternion scalar-first |

Timestamp reconstruction:

```text
t[0] = t0
t[i] = t[i-1] + dt_us[i] * 1e-6    for i = 1 .. count-1
```

`payload_uncompressed_nbytes` must equal:

```text
8 + 8
+ 4*accel_count + 12*accel_count
+ 4*motion_count + 12*motion_count + 12*motion_count + 12*motion_count + 16*motion_count
= 16 + 16*accel_count + 56*motion_count
```

## Integrity rules

1. `magic` / `version` must match.
2. `header_size` must equal file offset of payload and match preview flag.
3. Inflate payload when `PAYLOAD_ZLIB` is set; otherwise payload is raw.
4. `len(uncompressed) == payload_uncompressed_nbytes`.
5. `crc32(uncompressed) == payload_crc32` (compare as uint32).
6. Counts ≥ 2; reconstructed timestamps strictly increasing.
7. Reject non-finite float channels.

## Mapping to JSON v1 / `WatchCapture`

Decoder materializes the same logical fields as `golfmate-watch-capture-v1`
(`accelerometer800Hz`, `deviceMotion200Hz`, `captureMode`, device rates, …)
and feeds the existing Watch adapter so AHRS / impact-hint behaviour is unchanged.

## Swift sketch

```swift
// Pseudo: encode with Data + ContiguousBytes, little-endian
let crc = CRC32.checksum(uncompressedPayload) // same poly as zlib.crc32
// optional: uncompressedPayload = (try? zlibCompress(raw)) ?? raw
```

Python reference: `golfmate_algo.devices.packed_capture_v2`.
