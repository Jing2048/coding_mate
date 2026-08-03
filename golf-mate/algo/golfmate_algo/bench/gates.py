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

    # --- cross multibody: beyond-consumer budgets on citeable track ---
    # Consumer-grade literature budgets were ~40 ms / ~18 cm; we require tighter
    # than that on the independent multibody generator (product ambition).
    cross = by.get("cross_multibody", {})
    impact = _mean(cross, "events", "impact", "consumer")
    if impact is not None and impact > 20.0:
        violations.append(
            f"cross_multibody impact MAE {impact:.1f} ms exceeds 20 ms "
            f"beyond-consumer budget"
        )
    elif impact is not None:
        notes.append(f"cross_multibody impact MAE {impact:.2f} ms (budget 20)")

    e2e_pos = _mean(cross, "e2e", "consumer", "position_cm")
    if e2e_pos is None:
        e2e_pos = _mean(cross, "trajectory", "position_cm", "hybrid", "consumer")
    if e2e_pos is not None and e2e_pos > 17.0:
        violations.append(
            f"cross_multibody position MAE {e2e_pos:.1f} cm exceeds 17 cm "
            f"beyond-consumer budget"
        )
    elif e2e_pos is not None:
        notes.append(f"cross_multibody position MAE {e2e_pos:.2f} cm (budget 17)")

    e2e_ori = _mean(cross, "e2e", "consumer", "orientation_deg")
    if e2e_ori is not None and e2e_ori > 8.0:
        violations.append(
            f"cross_multibody orientation MAE {e2e_ori:.1f}° exceeds 8° "
            f"beyond-consumer budget"
        )
    elif e2e_ori is not None:
        notes.append(f"cross_multibody orientation MAE {e2e_ori:.2f}° (budget 8)")

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
                f"multisense (mocap-derived IMU) kinematic-impact MAE {e_imp:.1f} ms "
                f"(no collision shock); orientation {e_ori:.1f}°, position {e_pos:.1f} cm"
            )
            # Soft gate at 20° catches unit/frame regressions after adapter repair.
            if e_ori is not None and e_ori > 20.0:
                violations.append(
                    f"multisense orientation {e_ori:.1f}° exceeds 20° "
                    f"post-adapter sanity ceiling"
                )
            if e_pos is not None and e_pos > 100.0:
                violations.append(
                    f"multisense position {e_pos:.1f} cm exceeds 100 cm "
                    f"post-adapter sanity ceiling"
                )
        else:
            if e_imp is not None and e_imp > 80.0:
                violations.append(f"multisense impact MAE {e_imp:.1f} ms exceeds 80 ms")

    elite = by.get("external_multisense_elite", {})
    if elite.get("status") == "unavailable":
        notes.append(
            f"external_multisense_elite unavailable: {elite.get('reason', 'unknown')}"
        )
    elif elite.get("status") == "ok":
        notes.append(
            f"external_multisense_elite scored n={elite.get('n_swings')} "
            f"(eval gate only, not in-product posture library)"
        )

    # --- holdout seal ---
    hold = payload.get("holdout", {})
    if hold.get("enabled") and hold.get("mismatches"):
        violations.extend([f"holdout: {m}" for m in hold["mismatches"]])

    return {
        "pass": len(violations) == 0,
        "violations": violations,
        "notes": notes,
    }
