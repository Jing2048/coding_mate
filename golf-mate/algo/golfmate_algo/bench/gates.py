"""Hard pass/fail gates for the zero-trust evaluation suite."""

from __future__ import annotations

from typing import Any


def _mean(track: dict[str, Any], *path: str) -> float | None:
    cur: Any = track
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    if isinstance(cur, dict) and "mean" in cur:
        return float(cur["mean"])
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def check_gates(payload: dict[str, Any]) -> dict[str, Any]:
    """Inspect a ``run_evaluation`` payload and return pass/fail with reasons."""
    violations: list[str] = []
    notes: list[str] = []
    by = payload.get("by_track", {})

    # --- cross multibody: impact timing budget (consumer) ---
    cross = by.get("cross_multibody", {})
    impact = _mean(cross, "events", "impact", "consumer")
    if impact is not None and impact > 40.0:
        violations.append(
            f"cross_multibody impact MAE {impact:.1f} ms exceeds 40 ms consumer budget"
        )
    elif impact is not None:
        notes.append(f"cross_multibody impact MAE {impact:.2f} ms (budget 40)")

    # --- session: gated must crush gyro_only on analytic or multibody session ---
    session = payload.get("session", {})
    gated = _mean(session, "gated_adaptive", "consumer")
    gyro = _mean(session, "gyro_only", "consumer")
    if gated is not None and gyro is not None:
        if not (gated * 2.0 < gyro):
            violations.append(
                f"session gated ({gated:.1f}°) not ≪ gyro_only ({gyro:.1f}°)"
            )
        else:
            notes.append(f"session gated {gated:.2f}° vs gyro_only {gyro:.2f}°")

    # --- violation stress: residual / invalid rate must rise vs clean multibody ---
    viol = by.get("violation_stress", {})
    clean = by.get("cross_multibody", {})
    v_res = _mean(viol, "trajectory", "lever_arm_residual_m_s2", "consumer")
    c_res = _mean(clean, "trajectory", "lever_arm_residual_m_s2", "consumer")
    v_inv = _mean(viol, "trajectory", "lever_arm_invalid", "consumer")
    c_inv = _mean(clean, "trajectory", "lever_arm_invalid", "consumer")
    if v_res is not None and c_res is not None:
        if v_res < c_res * 1.15 and (v_inv or 0.0) <= (c_inv or 0.0) + 1e-9:
            violations.append(
                f"violation residual/invalid did not rise "
                f"(res {v_res:.2f} vs {c_res:.2f}, inv {v_inv} vs {c_inv})"
            )
        else:
            notes.append(
                f"violation residual {v_res:.2f} vs clean {c_res:.2f}; "
                f"invalid rate {v_inv} vs {c_inv}"
            )
    elif viol and not viol.get("empty"):
        notes.append("violation track present but residual metrics missing")

    # --- isomorphic must not be presented as product accuracy ---
    iso = by.get("isomorphic_analytic", {})
    if iso and not payload.get("meta", {}).get("disclaimer_isomorphic_upper_bound", False):
        # Soft note only — evaluate.py should set the flag
        notes.append("isomorphic track present; treat as upper bound only")

    # --- external ---
    ext = by.get("external_multisense", {})
    if ext.get("status") == "unavailable":
        notes.append(f"external_multisense unavailable: {ext.get('reason', 'unknown')}")
    elif ext.get("status") == "ok":
        notes.append("external_multisense scored")
        e_ori = _mean(ext, "orientation_deg")
        e_imp = _mean(ext, "impact_ms")
        e_pos = _mean(ext, "position_cm")
        # Mocap-derived IMU has no club-ball collision transient, so impact MAE
        # is informational only for this provenance.
        if ext.get("provenance") == "multisense_mocap_derived_imu":
            notes.append(
                f"multisense (mocap-derived IMU) impact MAE {e_imp:.1f} ms "
                f"— not hard-gated (no collision shock in stream); "
                f"orientation {e_ori:.1f}°, position {e_pos:.1f} cm"
            )
            # Soft orientation sanity: >90° mean means adapter/frame is broken
            if e_ori is not None and e_ori > 90.0:
                violations.append(
                    f"multisense orientation {e_ori:.1f}° exceeds 90° sanity ceiling"
                )
        else:
            if e_imp is not None and e_imp > 80.0:
                violations.append(f"multisense impact MAE {e_imp:.1f} ms exceeds 80 ms")

    # --- holdout seal ---
    hold = payload.get("holdout", {})
    if hold.get("enabled") and hold.get("mismatches"):
        violations.extend([f"holdout: {m}" for m in hold["mismatches"]])

    return {
        "pass": len(violations) == 0,
        "violations": violations,
        "notes": notes,
    }
