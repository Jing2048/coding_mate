"""Watch device-gold catalog loader + validator.

Validates ``data/watch_gold/manifest.json`` against the published schema,
verifies capture hashes, packed-v2 / JSON readability, sample rates / mode,
and required provenance. Supports count / stratification summaries.

Honesty: an empty in-repo catalog is expected. Synthetic fixtures are for
tests only and never imply commercial readiness.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from golfmate_algo.devices.packed_capture_v2 import is_packed_capture_v2
from golfmate_algo.devices.watch_capture import load_watch_capture

CONTRACT_VERSION = "watch-gold-manifest-v1"
DATASET_ID = "golfmate-watch-gold"
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "watch_gold"
DEFAULT_MANIFEST = DEFAULT_ROOT / "manifest.json"
DEFAULT_SCHEMA = DEFAULT_ROOT / "manifest.schema.json"

# Rate windows aligned with watch_capture / Watch app dual-rail.
_MOTION_FS_MIN = 40.0
_MOTION_FS_MAX = 240.0
_HIGH_RATE_ACCEL_MIN = 400.0
_HIGH_RATE_MOTION_TARGET = 180.0  # allow some clock skew under 200
_COMPAT_ACCEL_MAX = 200.0
_COMPAT_MOTION_MAX = 150.0

# Manifest declared rates vs decoded measured rates.
RATE_TOLERANCE_FRAC = 0.10
RATE_TOLERANCE_FLOOR_MOTION_HZ = 5.0
RATE_TOLERANCE_FLOOR_ACCEL_HZ = 20.0

SERIES_8_PLUS = frozenset(
    {"series_8", "series_9", "series_10", "ultra", "ultra_2"}
)
SERIES_5 = frozenset({"series_5"})

OPTIONAL_REF_KEYS = ("slow_mo", "optical", "launch_monitor", "metronome")
# Device-IMU-derived impact labels — provenance only, not independent gold.
DEVICE_DERIVED_IMPACT_SOURCES = frozenset({"collision_accel", "kinematic"})
INDEPENDENT_IMPACT_REF_KEYS = frozenset({"slow_mo", "optical", "launch_monitor"})
TEMPO_REF_KEYS = frozenset({"metronome", "slow_mo"})
_ARTIFACT_ID_OK = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
)

_REQUIRED_TOP = (
    "schema_version",
    "dataset_id",
    "status",
    "ready",
    "records",
)
_REQUIRED_RECORD = (
    "record_id",
    "subject_pseudonym",
    "device",
    "capture_mode",
    "rates",
    "handedness",
    "wrist",
    "club",
    "strap_fit",
    "terrain_lie",
    "session",
    "capture",
    "reference",
    "consent",
    "evidence_class",
)


@dataclass(frozen=True)
class WatchGoldRecord:
    """One validated catalog row (may still fail hash/read checks)."""

    raw: dict[str, Any]
    root: Path

    @property
    def record_id(self) -> str:
        return str(self.raw["record_id"])

    @property
    def subject_pseudonym(self) -> str:
        return str(self.raw["subject_pseudonym"])

    @property
    def evidence_class(self) -> str:
        return str(self.raw["evidence_class"])

    @property
    def capture_mode(self) -> str:
        return str(self.raw["capture_mode"])

    @property
    def device_series(self) -> str:
        return str(self.raw["device"]["series"])

    @property
    def handedness(self) -> str:
        return str(self.raw["handedness"])

    @property
    def strap_fit(self) -> str:
        return str(self.raw["strap_fit"])

    @property
    def club_class(self) -> str:
        return str(self.raw["club"]["class"])

    @property
    def terrain_lie(self) -> str:
        return str(self.raw["terrain_lie"])

    def capture_path(self) -> Path:
        p = Path(str(self.raw["capture"]["path"]))
        if p.is_absolute():
            return p
        return (self.root / p).resolve()

    def expected_sha256(self) -> str:
        return str(self.raw["capture"]["sha256"]).lower()


@dataclass
class ValidationIssue:
    level: str  # error | warning
    code: str
    message: str
    record_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "level": self.level,
            "code": self.code,
            "message": self.message,
        }
        if self.record_id is not None:
            d["record_id"] = self.record_id
        return d


@dataclass
class WatchGoldValidation:
    manifest: dict[str, Any]
    root: Path
    records: list[WatchGoldRecord] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    valid_record_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def valid_records(self) -> list[WatchGoldRecord]:
        ok = set(self.valid_record_ids)
        return [r for r in self.records if r.record_id in ok]


def load_schema(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_SCHEMA
    return json.loads(p.read_text(encoding="utf-8"))


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_MANIFEST
    return json.loads(p.read_text(encoding="utf-8"))


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    """Lightweight readiness probe for the empty-or-populated catalog."""
    root = root or DEFAULT_ROOT
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {
            "source": "watch_gold",
            "root": str(root),
            "ready": False,
            "status": "missing_manifest",
            "n_records": 0,
            "contract_version": CONTRACT_VERSION,
            "honesty": "Device-gold catalog missing.",
        }
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "source": "watch_gold",
            "root": str(root),
            "ready": False,
            "status": "invalid_manifest",
            "error": str(exc),
            "contract_version": CONTRACT_VERSION,
        }
    n = len(manifest.get("records") or [])
    ready_flag = bool(manifest.get("ready")) and n > 0
    return {
        "source": "watch_gold",
        "root": str(root),
        "ready": ready_flag,
        "status": manifest.get("status", "not_ready"),
        "manifest_ready_flag": bool(manifest.get("ready")),
        "n_records": n,
        "contract_version": CONTRACT_VERSION,
        "honesty": manifest.get("honesty"),
        "note": (
            "ready=true in manifest is advisory; commercial_release_gate is authoritative."
        ),
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _error(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    record_id: str | None = None,
) -> None:
    issues.append(
        ValidationIssue(level="error", code=code, message=message, record_id=record_id)
    )


def _warn(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    record_id: str | None = None,
) -> None:
    issues.append(
        ValidationIssue(
            level="warning", code=code, message=message, record_id=record_id
        )
    )


def _validate_top_level(manifest: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    for key in _REQUIRED_TOP:
        if key not in manifest:
            _error(issues, "missing_top_field", f"manifest missing required field {key!r}")
    if manifest.get("schema_version") != CONTRACT_VERSION:
        _error(
            issues,
            "bad_schema_version",
            f"schema_version must be {CONTRACT_VERSION!r}, "
            f"got {manifest.get('schema_version')!r}",
        )
    if not isinstance(manifest.get("records"), list):
        _error(issues, "records_not_list", "records must be a list")
        return
    if manifest.get("ready") is True and len(manifest.get("records") or []) == 0:
        _error(
            issues,
            "ready_empty",
            "ready=true is forbidden when records is empty",
        )


def _artifact_id_ok(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) >= 1
        and all(c in _ARTIFACT_ID_OK for c in value)
    )


def _ref_block_present(ref: Mapping[str, Any], key: str) -> bool:
    block = ref.get(key)
    return isinstance(block, Mapping) and block.get("present") is True


def optical_path_qualified(ref: Mapping[str, Any]) -> bool:
    """Optical block counts toward commercial path claim structural gate."""
    if not _ref_block_present(ref, "optical"):
        return False
    block = ref["optical"]
    if not _artifact_id_ok(block.get("artifact_id")):
        return False
    labels = block.get("labels")
    if not isinstance(labels, Mapping):
        return False
    return bool(
        labels.get("trajectory_available") is True
        or labels.get("wrist_path_available") is True
    )


def independent_impact_qualified(ref: Mapping[str, Any]) -> bool:
    """Independent (non-device-IMU) impact alignment reference present."""
    for key in INDEPENDENT_IMPACT_REF_KEYS:
        if not _ref_block_present(ref, key):
            continue
        block = ref[key]
        if not _artifact_id_ok(block.get("artifact_id")):
            continue
        if not isinstance(block.get("labels"), Mapping):
            continue
        if key == "slow_mo":
            # Prefer impact_frame_marked when declared; presence+labels still counts.
            return True
        if key == "optical":
            return True
        if key == "launch_monitor":
            return True
    return False


def tempo_ref_qualified(ref: Mapping[str, Any]) -> bool:
    for key in TEMPO_REF_KEYS:
        if not _ref_block_present(ref, key):
            continue
        block = ref[key]
        if not _artifact_id_ok(block.get("artifact_id")):
            continue
        labels = block.get("labels")
        if not isinstance(labels, Mapping):
            continue
        if key == "metronome":
            bpm = labels.get("bpm")
            if isinstance(bpm, (int, float)) and float(bpm) > 0:
                return True
        if key == "slow_mo":
            return True
    return False


def _validate_reference(
    reference: Mapping[str, Any],
    issues: list[ValidationIssue],
    rid_s: str | None,
) -> None:
    src = reference.get("impact_timestamp_source")
    if not src:
        _error(
            issues,
            "missing_reference",
            "reference.impact_timestamp_source is required",
            record_id=rid_s,
        )
    ts = reference.get("impact_timestamp_s")
    if not isinstance(ts, (int, float)) or isinstance(ts, bool) or float(ts) < 0:
        _error(
            issues,
            "missing_impact_timestamp",
            "reference.impact_timestamp_s must be a non-negative number "
            "(capture-relative seconds)",
            record_id=rid_s,
        )

    if src in DEVICE_DERIVED_IMPACT_SOURCES:
        # Provenance only — warn once per record (not an error).
        _warn(
            issues,
            "device_derived_impact_provenance",
            f"impact_timestamp_source={src!r} is device-derived provenance, "
            "not independent gold for Impact/path claims",
            record_id=rid_s,
        )

    for key in OPTIONAL_REF_KEYS:
        block = reference.get(key)
        if block is None:
            continue
        if not isinstance(block, Mapping):
            _error(
                issues,
                "bad_reference_block",
                f"reference.{key} must be an object or null",
                record_id=rid_s,
            )
            continue
        if "present" not in block:
            _error(
                issues,
                "bad_reference_block",
                f"reference.{key}.present is required",
                record_id=rid_s,
            )
            continue
        if block.get("present") is not True:
            continue
        # present=true → provenance id + labels required (files not required in-repo).
        if not _artifact_id_ok(block.get("artifact_id")):
            _error(
                issues,
                "missing_reference_artifact_id",
                f"reference.{key}.artifact_id required when present=true "
                "(opaque, no PII)",
                record_id=rid_s,
            )
        labels = block.get("labels")
        if not isinstance(labels, Mapping):
            _error(
                issues,
                "missing_reference_labels",
                f"reference.{key}.labels object required when present=true",
                record_id=rid_s,
            )
            continue
        if key == "optical":
            for lk in ("trajectory_available", "phase_labels_available"):
                if lk not in labels or not isinstance(labels[lk], bool):
                    _error(
                        issues,
                        "bad_optical_labels",
                        f"reference.optical.labels.{lk} must be a boolean",
                        record_id=rid_s,
                    )
        elif key == "metronome":
            bpm = labels.get("bpm")
            if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or float(bpm) <= 0:
                _error(
                    issues,
                    "bad_metronome_labels",
                    "reference.metronome.labels.bpm must be a positive number",
                    record_id=rid_s,
                )
        elif key == "launch_monitor":
            shot = labels.get("shot_id")
            if shot is not None and not _artifact_id_ok(shot):
                _error(
                    issues,
                    "bad_launch_monitor_labels",
                    "reference.launch_monitor.labels.shot_id must be opaque id",
                    record_id=rid_s,
                )


def rates_within_tolerance(
    declared_hz: float,
    measured_hz: float,
    *,
    floor_hz: float,
    frac: float = RATE_TOLERANCE_FRAC,
) -> bool:
    tol = max(float(floor_hz), float(frac) * float(declared_hz))
    return abs(float(declared_hz) - float(measured_hz)) <= tol


def _median_fs(t) -> float:
    import numpy as np

    arr = np.asarray(t, dtype=np.float64)
    if arr.size < 2:
        raise ValueError("need ≥2 timestamps to measure rate")
    dt = float(np.median(np.diff(arr)))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("invalid timestamps for rate")
    return 1.0 / dt


def _validate_record_schema(
    rec: Mapping[str, Any], issues: list[ValidationIssue]
) -> str | None:
    rid = rec.get("record_id")
    rid_s = str(rid) if rid is not None else None
    for key in _REQUIRED_RECORD:
        if key not in rec:
            _error(
                issues,
                "missing_record_field",
                f"record missing required field {key!r}",
                record_id=rid_s,
            )
    if rid_s is None:
        return None

    subject = rec.get("subject_pseudonym")
    if not isinstance(subject, str) or not subject.strip():
        _error(
            issues,
            "missing_subject",
            "subject_pseudonym is required",
            record_id=rid_s,
        )

    device = rec.get("device")
    if not isinstance(device, Mapping):
        _error(issues, "missing_device", "device object is required", record_id=rid_s)
    else:
        for k in ("model", "series", "watchos"):
            if not device.get(k):
                _error(
                    issues,
                    "missing_device",
                    f"device.{k} is required",
                    record_id=rid_s,
                )

    capture = rec.get("capture")
    if not isinstance(capture, Mapping):
        _error(issues, "missing_capture", "capture object is required", record_id=rid_s)
    else:
        if not capture.get("path"):
            _error(issues, "missing_capture_path", "capture.path required", record_id=rid_s)
        sha = capture.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64 or any(
            c not in "0123456789abcdef" for c in sha.lower()
        ):
            _error(
                issues,
                "missing_hash",
                "capture.sha256 must be a 64-char lowercase hex digest",
                record_id=rid_s,
            )

    reference = rec.get("reference")
    if not isinstance(reference, Mapping):
        _error(
            issues,
            "missing_reference",
            "reference object is required",
            record_id=rid_s,
        )
    else:
        _validate_reference(reference, issues, rid_s)

    consent = rec.get("consent")
    if not isinstance(consent, Mapping):
        _error(issues, "missing_consent", "consent object is required", record_id=rid_s)
    else:
        if consent.get("obtained") is not True:
            _error(
                issues,
                "consent_not_obtained",
                "consent.obtained must be true for indexed captures",
                record_id=rid_s,
            )
        if not consent.get("license"):
            _error(
                issues,
                "missing_license",
                "consent.license is required",
                record_id=rid_s,
            )

    mode = rec.get("capture_mode")
    if mode not in {"high_rate", "compat"}:
        _error(
            issues,
            "bad_capture_mode",
            f"capture_mode must be high_rate|compat, got {mode!r}",
            record_id=rid_s,
        )

    rates = rec.get("rates")
    if not isinstance(rates, Mapping):
        _error(issues, "missing_rates", "rates object is required", record_id=rid_s)
    else:
        for k in ("accelerometer_hz", "device_motion_hz"):
            if k not in rates or not isinstance(rates[k], (int, float)):
                _error(
                    issues,
                    "missing_rates",
                    f"rates.{k} must be a number",
                    record_id=rid_s,
                )

    if rec.get("evidence_class") not in {
        "real_device",
        "synthetic_fixture",
        "algorithm_synth",
    }:
        _error(
            issues,
            "bad_evidence_class",
            f"invalid evidence_class {rec.get('evidence_class')!r}",
            record_id=rid_s,
        )

    return rid_s


def _check_rates_vs_mode(
    rec: WatchGoldRecord, issues: list[ValidationIssue]
) -> None:
    rates = rec.raw["rates"]
    accel = float(rates["accelerometer_hz"])
    motion = float(rates["device_motion_hz"])
    mode = rec.capture_mode
    if not (_MOTION_FS_MIN <= motion <= _MOTION_FS_MAX):
        _error(
            issues,
            "motion_rate_out_of_range",
            f"device_motion_hz={motion} outside [{_MOTION_FS_MIN}, {_MOTION_FS_MAX}]",
            record_id=rec.record_id,
        )
    if mode == "high_rate":
        if accel < _HIGH_RATE_ACCEL_MIN:
            _error(
                issues,
                "high_rate_accel_too_low",
                f"high_rate accelerometer_hz={accel} < {_HIGH_RATE_ACCEL_MIN}",
                record_id=rec.record_id,
            )
        if motion < _HIGH_RATE_MOTION_TARGET:
            _error(
                issues,
                "high_rate_motion_too_low",
                f"high_rate device_motion_hz={motion} < {_HIGH_RATE_MOTION_TARGET}",
                record_id=rec.record_id,
            )
        if rec.device_series not in SERIES_8_PLUS:
            _error(
                issues,
                "high_rate_series_mismatch",
                f"high_rate requires Series 8+ series, got {rec.device_series!r}",
                record_id=rec.record_id,
            )
    elif mode == "compat":
        if accel > _COMPAT_ACCEL_MAX or motion > _COMPAT_MOTION_MAX:
            _error(
                issues,
                "compat_rate_too_high",
                f"compat rates accel={accel} motion={motion} look like high_rate",
                record_id=rec.record_id,
            )


def _check_capture_file(
    rec: WatchGoldRecord,
    issues: list[ValidationIssue],
    *,
    verify_hash: bool = True,
    load_capture: bool = True,
) -> bool:
    """Return True when file hash + readability checks pass."""
    path = rec.capture_path()
    if not path.is_file():
        _error(
            issues,
            "capture_missing",
            f"capture file not found: {path}",
            record_id=rec.record_id,
        )
        return False

    digest = sha256_file(path)
    expected = rec.expected_sha256()
    if verify_hash and digest != expected:
        _error(
            issues,
            "hash_mismatch",
            f"sha256 mismatch for {path.name}: expected {expected}, got {digest}",
            record_id=rec.record_id,
        )
        return False

    fmt = str(rec.raw["capture"].get("format", ""))
    raw = path.read_bytes()
    if fmt == "packed_v2":
        if not is_packed_capture_v2(raw):
            _error(
                issues,
                "not_packed_v2",
                "capture.format=packed_v2 but bytes are not GMPC packed v2",
                record_id=rec.record_id,
            )
            return False
    elif fmt == "json_v1":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _error(
                issues,
                "not_json_v1",
                f"capture.format=json_v1 but JSON parse failed: {exc}",
                record_id=rec.record_id,
            )
            return False
        if payload.get("schemaVersion") != "golfmate-watch-capture-v1":
            _error(
                issues,
                "bad_json_schema",
                "JSON capture missing golfmate-watch-capture-v1 schemaVersion",
                record_id=rec.record_id,
            )
            return False
    else:
        _error(
            issues,
            "bad_capture_format",
            f"unknown capture.format {fmt!r}",
            record_id=rec.record_id,
        )
        return False

    if load_capture:
        try:
            cap = load_watch_capture(path)
        except Exception as exc:  # noqa: BLE001 — surface as validation error
            _error(
                issues,
                "capture_unreadable",
                f"load_watch_capture failed: {exc}",
                record_id=rec.record_id,
            )
            return False
        if cap.capture_mode != rec.capture_mode:
            _error(
                issues,
                "capture_mode_mismatch",
                f"manifest mode {rec.capture_mode!r} != file mode {cap.capture_mode!r}",
                record_id=rec.record_id,
            )
            return False
        # Compare manifest rates to decoded measured rates (not mode alone).
        try:
            measured_motion = float(cap.packet.frame.fs_hz)
            measured_accel = _median_fs(cap.accel_t_800)
        except Exception as exc:  # noqa: BLE001
            _error(
                issues,
                "rate_measure_failed",
                f"could not measure capture rates: {exc}",
                record_id=rec.record_id,
            )
            return False
        decl_motion = float(rec.raw["rates"]["device_motion_hz"])
        decl_accel = float(rec.raw["rates"]["accelerometer_hz"])
        if not rates_within_tolerance(
            decl_motion,
            measured_motion,
            floor_hz=RATE_TOLERANCE_FLOOR_MOTION_HZ,
        ):
            _error(
                issues,
                "rate_mismatch_motion",
                f"device_motion_hz declared={decl_motion:.3f} measured={measured_motion:.3f} "
                f"exceeds tolerance {RATE_TOLERANCE_FRAC:.0%} / "
                f"floor {RATE_TOLERANCE_FLOOR_MOTION_HZ} Hz",
                record_id=rec.record_id,
            )
            return False
        if not rates_within_tolerance(
            decl_accel,
            measured_accel,
            floor_hz=RATE_TOLERANCE_FLOOR_ACCEL_HZ,
        ):
            _error(
                issues,
                "rate_mismatch_accel",
                f"accelerometer_hz declared={decl_accel:.3f} measured={measured_accel:.3f} "
                f"exceeds tolerance {RATE_TOLERANCE_FRAC:.0%} / "
                f"floor {RATE_TOLERANCE_FLOOR_ACCEL_HZ} Hz",
                record_id=rec.record_id,
            )
            return False
        # Impact timestamp must fall inside capture duration (structural sanity).
        ts = rec.raw.get("reference", {}).get("impact_timestamp_s")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            dur = float(cap.packet.t[-1]) if cap.packet.t.size else 0.0
            if float(ts) > dur + 0.25:
                _error(
                    issues,
                    "impact_timestamp_out_of_range",
                    f"impact_timestamp_s={float(ts):.4f} beyond capture duration {dur:.4f}s",
                    record_id=rec.record_id,
                )
                return False
    return True


def validate_manifest(
    manifest: Mapping[str, Any] | Path | None = None,
    *,
    root: Path | None = None,
    verify_hash: bool = True,
    load_capture: bool = True,
) -> WatchGoldValidation:
    """Validate schema + optional on-disk capture integrity."""
    if isinstance(manifest, Path) or manifest is None:
        path = Path(manifest) if manifest is not None else DEFAULT_MANIFEST
        root = root or path.parent
        data = load_manifest(path)
    else:
        data = dict(manifest)
        root = root or DEFAULT_ROOT

    issues: list[ValidationIssue] = []
    _validate_top_level(data, issues)
    records_raw = data.get("records") if isinstance(data.get("records"), list) else []
    records: list[WatchGoldRecord] = []
    seen_ids: set[str] = set()
    valid_ids: list[str] = []

    for rec in records_raw:
        if not isinstance(rec, Mapping):
            _error(issues, "record_not_object", "each record must be an object")
            continue
        rid = _validate_record_schema(rec, issues)
        if rid is None:
            continue
        if rid in seen_ids:
            _error(issues, "duplicate_record_id", f"duplicate record_id {rid!r}", rid)
            continue
        seen_ids.add(rid)
        wrapped = WatchGoldRecord(raw=dict(rec), root=root)
        records.append(wrapped)

        # Count schema errors already attached for this record.
        prior_errs = sum(
            1 for i in issues if i.level == "error" and i.record_id == rid
        )
        if prior_errs:
            continue

        _check_rates_vs_mode(wrapped, issues)
        rate_errs = sum(
            1 for i in issues if i.level == "error" and i.record_id == rid
        )
        if rate_errs:
            continue

        if _check_capture_file(
            wrapped, issues, verify_hash=verify_hash, load_capture=load_capture
        ):
            # Re-check no new errors for this id.
            if not any(i.level == "error" and i.record_id == rid for i in issues):
                valid_ids.append(rid)

    return WatchGoldValidation(
        manifest=dict(data),
        root=root,
        records=records,
        issues=issues,
        valid_record_ids=valid_ids,
    )


def stratification_summary(
    records: Sequence[WatchGoldRecord],
) -> dict[str, Any]:
    """Count / stratification rollup for gate + CLI."""

    def _counts(values: Iterable[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in values:
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    subjects = sorted({r.subject_pseudonym for r in records})
    return {
        "n_records": len(records),
        "n_subjects": len(subjects),
        "subjects": subjects,
        "by_evidence_class": _counts(r.evidence_class for r in records),
        "by_capture_mode": _counts(r.capture_mode for r in records),
        "by_device_series": _counts(r.device_series for r in records),
        "by_handedness": _counts(r.handedness for r in records),
        "by_strap_fit": _counts(r.strap_fit for r in records),
        "by_club_class": _counts(r.club_class for r in records),
        "by_terrain_lie": _counts(r.terrain_lie for r in records),
        "series_8_plus_high_rate": sum(
            1
            for r in records
            if r.device_series in SERIES_8_PLUS and r.capture_mode == "high_rate"
        ),
        "series_5_compat": sum(
            1
            for r in records
            if r.device_series in SERIES_5 and r.capture_mode == "compat"
        ),
        "reference_optional_present": {
            key: sum(
                1
                for r in records
                if isinstance(r.raw.get("reference", {}).get(key), Mapping)
                and r.raw["reference"][key].get("present") is True
            )
            for key in OPTIONAL_REF_KEYS
        },
        "claim_reference_counts": {
            "independent_impact": sum(
                1
                for r in records
                if independent_impact_qualified(r.raw.get("reference") or {})
            ),
            "optical_path": sum(
                1
                for r in records
                if optical_path_qualified(r.raw.get("reference") or {})
            ),
            "tempo": sum(
                1
                for r in records
                if tempo_ref_qualified(r.raw.get("reference") or {})
            ),
        },
    }


def validate_and_summarize(
    manifest: Mapping[str, Any] | Path | None = None,
    *,
    root: Path | None = None,
    verify_hash: bool = True,
    load_capture: bool = True,
) -> dict[str, Any]:
    """Machine-readable validation + stratification payload."""
    result = validate_manifest(
        manifest, root=root, verify_hash=verify_hash, load_capture=load_capture
    )
    valid = result.valid_records()
    return {
        "contract_version": CONTRACT_VERSION,
        "root": str(result.root),
        "schema_ok": not any(
            i.code
            in {
                "missing_top_field",
                "bad_schema_version",
                "records_not_list",
                "ready_empty",
            }
            for i in result.issues
            if i.level == "error"
        ),
        "validation_ok": result.ok and len(result.records) == len(result.valid_record_ids),
        "n_declared": len(result.records),
        "n_valid": len(valid),
        "issues": [i.as_dict() for i in result.issues],
        "summary_all_declared": stratification_summary(result.records),
        "summary_valid": stratification_summary(valid),
        "manifest_status": result.manifest.get("status"),
        "manifest_ready_flag": bool(result.manifest.get("ready")),
        "documented_limitations": list(
            result.manifest.get("documented_limitations") or []
        ),
    }
