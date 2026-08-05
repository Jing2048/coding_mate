"""Commercial release gate — fail-closed device evidence gate.

Distinguishes algorithm synthetic CI gates from real Watch device-gold evidence.
Synthetic / fixture data may exercise the *structural* checks in tests, but
``commercial_ready`` is true only for ``evidence_class=real_device`` records that
pass all strata. Empty in-repo catalogs always report not ready.

Claim-specific independent reference gates are **minimum structural evidence**
(presence of provenance + labels), **not** an accuracy pass on Impact/path/tempo.
Device-derived ``collision_accel`` / ``kinematic`` labels are provenance only and
do not satisfy independent Impact/path gold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from golfmate_algo.bench.datasets import watch_gold as wg
from golfmate_algo.bench.datasets.watch_gold import (
    CONTRACT_VERSION,
    SERIES_5,
    SERIES_8_PLUS,
    WatchGoldRecord,
    WatchGoldValidation,
    independent_impact_qualified,
    optical_path_qualified,
    stratification_summary,
    tempo_ref_qualified,
    validate_manifest,
)

GATE_VERSION = "commercial-release-gate-v2"

MIN_VALID_SWINGS = 30
MIN_SUBJECTS = 2
MIN_STRAP_FIT_VARIANTS = 2
MIN_OPTICAL_PATH_RECORDS = 3
MIN_TEMPO_REF_RECORDS = 3
WOOD_CLASSES = frozenset({"wood"})
IRON_CLASSES = frozenset({"iron", "wedge"})  # wedge counts toward iron family


def _criterion(
    name: str,
    passed: bool,
    *,
    detail: str,
    required_for_commercial: bool = True,
    claim: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
        "required_for_commercial": required_for_commercial,
    }
    if claim is not None:
        out["claim"] = claim
    return out


def _handedness_ok(
    records: Sequence[WatchGoldRecord],
    limitations: Sequence[str],
) -> tuple[bool, str]:
    hands = {r.handedness for r in records}
    has_left = "left" in hands
    has_right = "right" in hands
    if has_left and has_right:
        return True, "left and right handedness represented"
    if not has_left and "left_hand_not_represented" in limitations:
        return True, "left missing but documented_limitations includes left_hand_not_represented"
    if not has_right and "right_hand_not_represented" in limitations:
        return True, "right missing but documented_limitations includes right_hand_not_represented"
    missing = []
    if not has_left:
        missing.append("left")
    if not has_right:
        missing.append("right")
    return (
        False,
        f"handedness missing {missing}; add swings or documented_limitations",
    )


def _pct_floor(n: int) -> int:
    return max(3, int((n + 9) // 10))  # ≥3 or ≥10%


def evaluate_claim_reference_gates(
    records: Sequence[WatchGoldRecord],
) -> dict[str, Any]:
    """Claim-specific independent reference structural gates.

    These prove minimum independent provenance exists for Impact alignment,
    optical wrist/path, and tempo. They are **not** numerical accuracy budgets.
    Metronome alone cannot unlock Impact/path commercial evidence.
    """
    n = len(records)
    criteria: list[dict[str, Any]] = []
    if n == 0:
        empty = _criterion(
            "claim_references_nonempty",
            False,
            detail="no valid records for claim reference gates",
        )
        return {
            "passed": False,
            "criteria": [empty],
            "honesty": (
                "Structural evidence minimum only — not an Impact/path/tempo accuracy pass."
            ),
            "counts": {
                "independent_impact": 0,
                "optical_path": 0,
                "tempo": 0,
                "n_records": 0,
            },
        }

    for r in records:
        ref = r.raw.get("reference") or {}
        if not isinstance(ref, Mapping) or ref.get("impact_timestamp_s") is None:
            criteria.append(
                _criterion(
                    "impact_timestamp_s_present",
                    False,
                    detail=f"record {r.record_id} missing impact_timestamp_s",
                )
            )
            break
    else:
        criteria.append(
            _criterion(
                "impact_timestamp_s_present",
                True,
                detail="all records declare capture-relative impact_timestamp_s",
            )
        )

    need_impact = _pct_floor(n)
    n_impact = sum(
        1
        for r in records
        if independent_impact_qualified(r.raw.get("reference") or {})
    )
    criteria.append(
        _criterion(
            "independent_impact_alignment",
            n_impact >= need_impact,
            detail=(
                f"independent impact refs (slow_mo|optical|launch_monitor) "
                f"{n_impact}/{n} (need ≥{need_impact}); "
                "device collision_accel/kinematic do not count"
            ),
            claim="impact_timing",
        )
    )

    n_optical = sum(
        1 for r in records if optical_path_qualified(r.raw.get("reference") or {})
    )
    criteria.append(
        _criterion(
            "optical_wrist_path_reference",
            n_optical >= MIN_OPTICAL_PATH_RECORDS,
            detail=(
                f"optical path-qualified records {n_optical} "
                f"(need ≥{MIN_OPTICAL_PATH_RECORDS} with artifact_id + "
                "trajectory_available|wrist_path_available)"
            ),
            claim="wrist_path",
        )
    )

    n_tempo = sum(
        1 for r in records if tempo_ref_qualified(r.raw.get("reference") or {})
    )
    criteria.append(
        _criterion(
            "tempo_reference",
            n_tempo >= MIN_TEMPO_REF_RECORDS,
            detail=(
                f"tempo refs (metronome|slow_mo) {n_tempo}/{n} "
                f"(need ≥{MIN_TEMPO_REF_RECORDS})"
            ),
            claim="tempo",
        )
    )

    passed = all(c["passed"] for c in criteria)
    return {
        "passed": passed,
        "criteria": criteria,
        "honesty": (
            "These claim gates are minimum structural evidence "
            "(independent provenance + labels). They are NOT an accuracy pass "
            "on Impact timing, wrist path, or tempo."
        ),
        "counts": {
            "independent_impact": n_impact,
            "optical_path": n_optical,
            "tempo": n_tempo,
            "n_records": n,
            "independent_impact_need": need_impact,
        },
    }


def evaluate_structural_gate(
    records: Sequence[WatchGoldRecord],
    *,
    documented_limitations: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Count / strata / claim-reference checks (may run on synthetic fixtures in tmp)."""
    limitations = list(documented_limitations or [])
    summary = stratification_summary(records)
    criteria: list[dict[str, Any]] = []

    n = len(records)
    criteria.append(
        _criterion(
            "min_valid_swings",
            n >= MIN_VALID_SWINGS,
            detail=f"{n} valid swings (need ≥{MIN_VALID_SWINGS})",
        )
    )
    n_subj = int(summary["n_subjects"])
    criteria.append(
        _criterion(
            "min_subjects",
            n_subj >= MIN_SUBJECTS,
            detail=f"{n_subj} subjects (need ≥{MIN_SUBJECTS})",
        )
    )
    s8 = int(summary["series_8_plus_high_rate"])
    criteria.append(
        _criterion(
            "series_8_plus_high_rate",
            s8 >= 1,
            detail=f"{s8} Series 8+ high_rate swings (need ≥1)",
        )
    )
    s5 = int(summary["series_5_compat"])
    criteria.append(
        _criterion(
            "series_5_compat",
            s5 >= 1,
            detail=f"{s5} Series 5 compat swings (need ≥1)",
        )
    )
    hand_ok, hand_detail = _handedness_ok(records, limitations)
    criteria.append(_criterion("handedness_coverage", hand_ok, detail=hand_detail))

    strap_n = len(summary["by_strap_fit"])
    criteria.append(
        _criterion(
            "strap_fit_variants",
            strap_n >= MIN_STRAP_FIT_VARIANTS,
            detail=f"{strap_n} strap_fit values {sorted(summary['by_strap_fit'])} "
            f"(need ≥{MIN_STRAP_FIT_VARIANTS})",
        )
    )

    clubs = set(summary["by_club_class"])
    has_iron = bool(clubs & IRON_CLASSES)
    has_wood = bool(clubs & WOOD_CLASSES)
    criteria.append(
        _criterion(
            "club_iron_and_wood",
            has_iron and has_wood,
            detail=f"club classes={sorted(clubs)}; iron={has_iron} wood={has_wood}",
        )
    )

    claim_refs = evaluate_claim_reference_gates(records)
    criteria.extend(claim_refs["criteria"])

    passed = all(c["passed"] for c in criteria)
    return {
        "passed": passed,
        "criteria": criteria,
        "summary": summary,
        "documented_limitations": limitations,
        "claim_reference_gates": claim_refs,
        "honesty": (
            "Structural device-gold evidence only. Passing does not certify "
            "numerical Impact/path/tempo accuracy budgets."
        ),
    }


def evaluate_commercial_release_gate(
    manifest: Mapping[str, Any] | Path | None = None,
    *,
    root: Path | None = None,
    verify_hash: bool = True,
    load_capture: bool = True,
    validation: WatchGoldValidation | None = None,
) -> dict[str, Any]:
    """Fail-closed commercial readiness report (machine-readable)."""
    if validation is None:
        validation = validate_manifest(
            manifest,
            root=root,
            verify_hash=verify_hash,
            load_capture=load_capture,
        )
    limitations = list(validation.manifest.get("documented_limitations") or [])
    all_valid = validation.valid_records()
    real = [r for r in all_valid if r.evidence_class == "real_device"]
    synthetic = [
        r
        for r in all_valid
        if r.evidence_class in {"synthetic_fixture", "algorithm_synth"}
    ]

    structural_real = evaluate_structural_gate(
        real, documented_limitations=limitations
    )
    structural_any = evaluate_structural_gate(
        all_valid, documented_limitations=limitations
    )

    validation_ok = validation.ok and len(validation.records) == len(
        validation.valid_record_ids
    )
    # Empty catalog: validation_ok is True (no records to fail) — still not ready.
    empty = len(validation.records) == 0

    evidence_block = {
        "real_device_valid": len(real),
        "synthetic_or_fixture_valid": len(synthetic),
        "declared_total": len(validation.records),
        "valid_total": len(all_valid),
        "synthetic_never_converts_to_commercial": True,
        "device_derived_impact_not_independent_gold": True,
        "note": (
            "Algorithm synthetic gates (cross_multibody, optical twins, "
            "mocap-derived IMU) are separate from this device-evidence gate. "
            "Metronome-only catalogs cannot unlock Impact/path commercial_ready."
        ),
    }

    commercial_ready = (
        (not empty)
        and validation_ok
        and len(real) > 0
        and structural_real["passed"]
        and len(synthetic) == 0  # mixed catalogs fail closed for commercial
    )
    # If synthetic records exist alongside real, fail commercial with reason.
    if synthetic and real:
        commercial_ready = False
        mixed_detail = (
            f"catalog mixes real_device ({len(real)}) with synthetic/fixture "
            f"({len(synthetic)}); commercial gate requires real_device-only evidence"
        )
    else:
        mixed_detail = "evidence class homogeneous or empty"

    reasons: list[str] = []
    if empty:
        reasons.append("empty device-gold catalog — not ready")
    if not validation_ok:
        reasons.append("manifest/capture validation failed")
    if not empty and len(real) == 0:
        reasons.append(
            "no real_device evidence — synthetic fixtures cannot unlock commercial_ready"
        )
    if real and not structural_real["passed"]:
        failed = [c["name"] for c in structural_real["criteria"] if not c["passed"]]
        reasons.append(f"structural criteria failed for real_device: {failed}")
    if synthetic and real:
        reasons.append(mixed_detail)

    report: dict[str, Any] = {
        "gate_version": GATE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "commercial_ready": bool(commercial_ready),
        "structural_gate": {
            "on_real_device": structural_real,
            "on_all_valid_including_synthetic": structural_any,
            "note": (
                "Structural checks may pass on tmp synthetic fixtures for CI tests; "
                "that does not imply commercial_ready. Claim reference gates are "
                "minimum structural evidence, not accuracy budgets."
            ),
        },
        "validation": {
            "ok": validation_ok,
            "empty_catalog": empty,
            "n_declared": len(validation.records),
            "n_valid": len(all_valid),
            "issues": [i.as_dict() for i in validation.issues],
        },
        "evidence": evidence_block,
        "algorithm_synthetic_gates": {
            "substitutable_for_device_evidence": False,
            "examples": [
                "cross_multibody",
                "optical_aligned_synth",
                "multisense_mocap_derived",
                "cmu64_synth_imu",
            ],
            "note": (
                "Passing algorithm CI gates proves regressable kinematics, "
                "not Watch MEMS commercial readiness."
            ),
        },
        "mixed_evidence": {"ok": not (synthetic and real), "detail": mixed_detail},
        "reasons": reasons,
        "root": str(validation.root),
        "manifest_status": validation.manifest.get("status"),
        "manifest_ready_flag": bool(validation.manifest.get("ready")),
    }
    return report


def commercial_ready(
    manifest: Mapping[str, Any] | Path | None = None,
    **kwargs: Any,
) -> bool:
    return bool(
        evaluate_commercial_release_gate(manifest, **kwargs)["commercial_ready"]
    )


__all__ = [
    "GATE_VERSION",
    "MIN_OPTICAL_PATH_RECORDS",
    "MIN_SUBJECTS",
    "MIN_TEMPO_REF_RECORDS",
    "MIN_VALID_SWINGS",
    "commercial_ready",
    "evaluate_claim_reference_gates",
    "evaluate_commercial_release_gate",
    "evaluate_structural_gate",
    "SERIES_5",
    "SERIES_8_PLUS",
    "wg",
]
