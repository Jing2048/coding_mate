"""Watch device-gold catalog + commercial release gate tests.

All capture fixtures live under pytest tmp paths — never in the repo catalog.
The in-repo empty manifest must report not ready while these tests pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from golfmate_algo.bench.commercial_release_gate import (
    GATE_VERSION,
    MIN_SUBJECTS,
    MIN_VALID_SWINGS,
    evaluate_claim_reference_gates,
    evaluate_commercial_release_gate,
    evaluate_structural_gate,
)
from golfmate_algo.bench.datasets.watch_gold import (
    CONTRACT_VERSION,
    DEFAULT_MANIFEST,
    DEFAULT_ROOT,
    dataset_status,
    load_manifest,
    load_schema,
    sha256_file,
    stratification_summary,
    validate_and_summarize,
    validate_manifest,
)
from golfmate_algo.devices.packed_capture_v2 import encode_packed_capture_v2
from golfmate_algo.devices.watch_capture import G0
from golfmate_algo.synth.analytic import planar_circular_swing


def _v1_payload(
    *,
    fs_motion: float,
    fs_accel: float,
    capture_mode: str,
    model: str,
    handedness: str = "right",
    session_id: str = "E9DA174A-E1E0-4BA8-8AD0-EC54B84D7D07",
):
    swing = planar_circular_swing(fs_hz=fs_motion, impact_shock_g=4.0)
    t_motion = swing.packet.t
    t_accel = np.arange(int(round(t_motion[-1] * fs_accel)) + 1) / fs_accel
    accel_g = np.column_stack(
        [
            np.interp(t_accel, t_motion, swing.packet.accel[:, axis] / G0)
            for axis in range(3)
        ]
    )
    impact_s = float(t_motion[int(swing.phases_true.impact_idx)])
    return {
        "schemaVersion": "golfmate-watch-capture-v1",
        "sessionID": session_id,
        "startedAtUnix": 1000.0,
        "endedAtUnix": 1000.0 + float(t_motion[-1]),
        "handedness": handedness,
        "wrist": "lead",
        "mountExtrinsicWXYZ": [1, 0, 0, 0],
        "captureMode": capture_mode,
        "device": {
            "model": model,
            "systemVersion": "10.5",
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
    }, impact_s


def _write_capture(
    directory: Path,
    name: str,
    *,
    high_rate: bool,
    handedness: str = "right",
    as_json: bool = False,
) -> tuple[Path, str, dict]:
    if high_rate:
        payload, impact_s = _v1_payload(
            fs_motion=200.0,
            fs_accel=800.0,
            capture_mode="high_rate",
            model="Watch7,5",
            handedness=handedness,
        )
        fmt = "json_v1" if as_json else "packed_v2"
    else:
        payload, impact_s = _v1_payload(
            fs_motion=100.0,
            fs_accel=100.0,
            capture_mode="compat",
            model="Watch5,2",
            handedness=handedness,
        )
        fmt = "json_v1" if as_json else "packed_v2"

    path = directory / name
    if as_json:
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_bytes(encode_packed_capture_v2(payload, compress=True))
    digest = sha256_file(path)
    meta = {
        "capture_mode": payload["captureMode"],
        "rates": {
            "accelerometer_hz": float(payload["device"]["accelerometerHz"]),
            "device_motion_hz": float(payload["device"]["deviceMotionHz"]),
        },
        "model": payload["device"]["model"],
        "series": "ultra_2" if high_rate else "series_5",
        "format": fmt,
        "handedness": handedness,
        "impact_timestamp_s": impact_s,
    }
    return path, digest, meta


def _optical_block(i: int) -> dict:
    return {
        "present": True,
        "artifact_id": f"opt-{i:03d}",
        "labels": {
            "trajectory_available": True,
            "phase_labels_available": True,
            "wrist_path_available": True,
        },
    }


def _metronome_block(i: int) -> dict:
    return {
        "present": True,
        "artifact_id": f"metro-{i:03d}",
        "labels": {"bpm": 60.0, "phase_offset_s": 0.0},
    }


def _slow_mo_block(i: int) -> dict:
    return {
        "present": True,
        "artifact_id": f"sm-{i:03d}",
        "labels": {"impact_frame_marked": True, "tempo_visible": True},
    }


def _record(
    *,
    record_id: str,
    subject: str,
    path: Path,
    digest: str,
    meta: dict,
    club_class: str,
    club_label: str,
    strap_fit: str,
    terrain: str,
    evidence_class: str,
    ref_extra: dict | None = None,
) -> dict:
    reference = {
        "impact_timestamp_source": "collision_accel"
        if meta["capture_mode"] == "high_rate"
        else "kinematic",
        "impact_timestamp_s": float(meta["impact_timestamp_s"]),
    }
    if ref_extra:
        reference.update(ref_extra)
    return {
        "record_id": record_id,
        "subject_pseudonym": subject,
        "device": {
            "model": meta["model"],
            "series": meta["series"],
            "watchos": "10.5",
        },
        "capture_mode": meta["capture_mode"],
        "rates": meta["rates"],
        "handedness": meta["handedness"],
        "wrist": "lead",
        "club": {"class": club_class, "label": club_label},
        "strap_fit": strap_fit,
        "terrain_lie": terrain,
        "session": {
            "session_id": f"sess-{subject}",
            "captured_at_date": "2026-08-01",
        },
        "capture": {
            "path": str(path),
            "sha256": digest,
            "format": meta["format"],
        },
        "reference": reference,
        "consent": {
            "obtained": True,
            "license": "internal-test-fixture-v1",
        },
        "evidence_class": evidence_class,
    }


def _build_catalog(
    tmp_path: Path,
    *,
    evidence_class: str = "synthetic_fixture",
    n: int = MIN_VALID_SWINGS,
    include_left: bool = True,
    ref_mode: str = "full",
    tamper_hash: bool = False,
    tamper_rates: bool = False,
    skip_subject: bool = False,
    skip_device: bool = False,
    skip_reference: bool = False,
    skip_hash_field: bool = False,
    skip_impact_ts: bool = False,
) -> tuple[dict, Path]:
    """Build a catalog under tmp_path only.

    ref_mode:
      - ``full``: ≥3 optical path + independent impact + tempo (structural OK)
      - ``metronome_only``: metronome refs only (must fail claim gates)
    """
    cap_dir = tmp_path / "captures"
    cap_dir.mkdir(exist_ok=True)
    records: list[dict] = []

    for i in range(n):
        high_rate = i % 3 != 0
        subject = "sub_a" if i % 2 == 0 else "sub_b"
        handedness = "left" if (include_left and i % 5 == 0) else "right"
        path, digest, meta = _write_capture(
            cap_dir,
            f"swing_{i:03d}.{'json' if i % 7 == 0 else 'gmpc'}",
            high_rate=high_rate,
            handedness=handedness,
            as_json=(i % 7 == 0),
        )
        if tamper_hash and i == 0:
            digest = "0" * 64
        if tamper_rates and i == 0:
            # Mode-legal declared rates that disagree with decoded measured rates.
            if high_rate:
                meta["rates"] = {
                    "accelerometer_hz": 550.0,  # still ≥400 high_rate floor
                    "device_motion_hz": 239.0,  # still in [180, 240]
                }
            else:
                meta["rates"] = {
                    "accelerometer_hz": 180.0,  # ≤200 compat cap
                    "device_motion_hz": 140.0,  # ≤150 compat cap
                }
        club_class = "iron" if i % 2 == 0 else "wood"
        club_label = "7i" if club_class == "iron" else "driver"
        strap = "snug" if i % 2 == 0 else "loose"
        terrain = "flat" if i % 4 else "uphill"

        ref_extra: dict = {}
        if ref_mode == "full":
            # ≥3 optical path-qualified; also covers independent impact.
            if i < 3:
                ref_extra["optical"] = _optical_block(i)
            # Tempo via metronome on first 3 (optical already covers impact).
            if i < 3:
                ref_extra["metronome"] = _metronome_block(i)
            # Extra independent impact via slow_mo to satisfy ≥10% when n large.
            need = max(3, (n + 9) // 10)
            if 3 <= i < need:
                ref_extra["slow_mo"] = _slow_mo_block(i)
        elif ref_mode == "metronome_only":
            if i < max(3, (n + 9) // 10):
                ref_extra["metronome"] = _metronome_block(i)

        rec = _record(
            record_id=f"r{i:03d}",
            subject=subject,
            path=path,
            digest=digest,
            meta=meta,
            club_class=club_class,
            club_label=club_label,
            strap_fit=strap,
            terrain=terrain,
            evidence_class=evidence_class,
            ref_extra=ref_extra or None,
        )
        if skip_subject and i == 0:
            rec.pop("subject_pseudonym")
        if skip_device and i == 0:
            rec.pop("device")
        if skip_reference and i == 0:
            rec["reference"] = {}
        if skip_impact_ts and i == 0:
            rec["reference"].pop("impact_timestamp_s", None)
        if skip_hash_field and i == 0:
            rec["capture"].pop("sha256")
        records.append(rec)

    manifest = {
        "schema_version": CONTRACT_VERSION,
        "dataset_id": "golfmate-watch-gold-test",
        "status": "collecting",
        "ready": False,
        "honesty": "tmp synthetic fixtures only",
        "documented_limitations": []
        if include_left
        else ["left_hand_not_represented"],
        "records": records,
    }
    man_path = tmp_path / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest, man_path


def _build_sufficient_catalog(tmp_path: Path, **kwargs):
    kwargs.setdefault("ref_mode", "full")
    return _build_catalog(tmp_path, **kwargs)


# ---------------------------------------------------------------------------
# Repo empty catalog
# ---------------------------------------------------------------------------


def test_repo_schema_and_empty_manifest_loadable():
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == CONTRACT_VERSION
    assert "impact_timestamp_s" in schema["$defs"]["record"]["properties"]["reference"][
        "required"
    ]
    man = load_manifest(DEFAULT_MANIFEST)
    assert man["schema_version"] == CONTRACT_VERSION
    assert man["ready"] is False
    assert man["status"] == "not_ready"
    assert man["records"] == []
    st = dataset_status(DEFAULT_ROOT)
    assert st["ready"] is False
    assert st["n_records"] == 0


def test_repo_empty_catalog_gate_not_ready():
    report = evaluate_commercial_release_gate(DEFAULT_MANIFEST)
    assert report["gate_version"] == GATE_VERSION
    assert report["commercial_ready"] is False
    assert report["validation"]["empty_catalog"] is True
    assert report["algorithm_synthetic_gates"]["substitutable_for_device_evidence"] is False
    assert report["evidence"]["device_derived_impact_not_independent_gold"] is True
    assert any("empty" in r for r in report["reasons"])
    structural = report["structural_gate"]["on_real_device"]
    assert structural["passed"] is False


def test_cli_empty_manifest_json(capsys):
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "commercial_release_gate.py"
    )
    spec = importlib.util.spec_from_file_location("commercial_release_gate_cli", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main(["--manifest", str(DEFAULT_MANIFEST)])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["commercial_ready"] is False
    assert payload["validation"]["empty_catalog"] is True


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_missing_subject_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, skip_subject=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "missing_subject" for i in result.issues)


def test_missing_device_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, skip_device=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "missing_device" for i in result.issues)


def test_missing_reference_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, skip_reference=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "missing_reference" for i in result.issues)


def test_missing_impact_timestamp_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, skip_impact_ts=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "missing_impact_timestamp" for i in result.issues)


def test_missing_hash_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, skip_hash_field=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "missing_hash" for i in result.issues)


def test_tampered_hash_fails(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, tamper_hash=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(i.code == "hash_mismatch" for i in result.issues)
    report = evaluate_commercial_release_gate(path, root=tmp_path)
    assert report["commercial_ready"] is False
    assert report["validation"]["ok"] is False


def test_tampered_rates_fail(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=4, tamper_rates=True)
    result = validate_manifest(path, root=tmp_path)
    assert any(
        i.code in {"rate_mismatch_motion", "rate_mismatch_accel"} for i in result.issues
    )
    assert "r000" not in result.valid_record_ids


# ---------------------------------------------------------------------------
# Claim reference gates + sufficient fixtures
# ---------------------------------------------------------------------------


def test_metronome_only_catalog_fails_structural(tmp_path):
    """Metronome can support tempo but cannot validate Impact/path."""
    _, path = _build_catalog(
        tmp_path,
        evidence_class="synthetic_fixture",
        n=MIN_VALID_SWINGS,
        ref_mode="metronome_only",
    )
    result = validate_manifest(path, root=tmp_path)
    assert result.ok
    structural = evaluate_structural_gate(
        result.valid_records(),
        documented_limitations=result.manifest.get("documented_limitations") or [],
    )
    assert structural["passed"] is False
    claim = structural["claim_reference_gates"]
    names = {c["name"]: c["passed"] for c in claim["criteria"]}
    assert names.get("tempo_reference") is True
    assert names.get("independent_impact_alignment") is False
    assert names.get("optical_wrist_path_reference") is False
    report = evaluate_commercial_release_gate(path, root=tmp_path)
    assert report["commercial_ready"] is False


def test_synthetic_fixture_passes_structural_not_commercial(tmp_path):
    _, path = _build_sufficient_catalog(
        tmp_path, evidence_class="synthetic_fixture", n=MIN_VALID_SWINGS
    )
    result = validate_manifest(path, root=tmp_path)
    assert result.ok
    assert len(result.valid_record_ids) >= MIN_VALID_SWINGS
    summary = stratification_summary(result.valid_records())
    assert summary["n_subjects"] >= MIN_SUBJECTS
    assert summary["series_8_plus_high_rate"] >= 1
    assert summary["series_5_compat"] >= 1
    assert summary["claim_reference_counts"]["optical_path"] >= 3
    assert summary["claim_reference_counts"]["independent_impact"] >= 3
    assert summary["claim_reference_counts"]["tempo"] >= 3

    structural = evaluate_structural_gate(
        result.valid_records(),
        documented_limitations=result.manifest.get("documented_limitations") or [],
    )
    assert structural["passed"] is True
    assert "accuracy" in structural["honesty"].lower() or "not" in structural["honesty"].lower()

    report = evaluate_commercial_release_gate(path, root=tmp_path)
    assert report["structural_gate"]["on_all_valid_including_synthetic"]["passed"] is True
    assert report["commercial_ready"] is False
    assert any("real_device" in r or "synthetic" in r for r in report["reasons"])


def test_real_device_declared_fixtures_can_pass_commercial_in_tmp(tmp_path):
    """Tmp-only: proves gate logic; repo catalog stays empty / not ready."""
    _, path = _build_sufficient_catalog(
        tmp_path, evidence_class="real_device", n=MIN_VALID_SWINGS
    )
    report = evaluate_commercial_release_gate(path, root=tmp_path)
    assert report["validation"]["ok"] is True
    assert report["structural_gate"]["on_real_device"]["passed"] is True
    claim = report["structural_gate"]["on_real_device"]["claim_reference_gates"]
    assert claim["passed"] is True
    assert report["commercial_ready"] is True
    repo = evaluate_commercial_release_gate(DEFAULT_MANIFEST)
    assert repo["commercial_ready"] is False


def test_left_limitation_allows_right_only(tmp_path):
    _, path = _build_sufficient_catalog(
        tmp_path,
        evidence_class="synthetic_fixture",
        n=MIN_VALID_SWINGS,
        include_left=False,
    )
    result = validate_manifest(path, root=tmp_path)
    structural = evaluate_structural_gate(
        result.valid_records(),
        documented_limitations=["left_hand_not_represented"],
    )
    assert structural["passed"] is True
    hand = next(c for c in structural["criteria"] if c["name"] == "handedness_coverage")
    assert hand["passed"] is True


def test_claim_gates_honesty_not_accuracy(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=MIN_VALID_SWINGS)
    result = validate_manifest(path, root=tmp_path)
    claim = evaluate_claim_reference_gates(result.valid_records())
    assert claim["passed"] is True
    assert "not" in claim["honesty"].lower() and "accuracy" in claim["honesty"].lower()


def test_validate_and_summarize_machine_readable(tmp_path):
    _, path = _build_sufficient_catalog(tmp_path, n=6)
    payload = validate_and_summarize(path, root=tmp_path)
    assert "summary_valid" in payload
    assert payload["n_valid"] >= 1
    assert "claim_reference_counts" in payload["summary_valid"]
    json.dumps(payload, allow_nan=False)


def test_require_ready_exit_code_on_empty():
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "commercial_release_gate.py"
    )
    spec = importlib.util.spec_from_file_location("commercial_release_gate_cli2", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main(["--manifest", str(DEFAULT_MANIFEST), "--require-ready"])
    assert code == 1
