"""Hard pass/fail gates for the zero-trust evaluation suite."""

from __future__ import annotations

from typing import Any

from golfmate_algo.bench.golden import scirep_budgets


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
    # Hard product ceilings: impact ≤15 ms, orientation ≤6°, position ≤17 cm.
    # Aspirational 12 cm position is reported separately (baseline ~12.0 cm).
    cross = by.get("cross_multibody", {})
    e2e_pos = _mean(cross, "e2e", "consumer_wrist", "position_cm")
    if e2e_pos is None:
        e2e_pos = _mean(cross, "e2e", "consumer", "position_cm")
    if e2e_pos is None:
        e2e_pos = _mean(cross, "trajectory", "position_cm", "hybrid", "consumer")
    # Product budgets apply to wrist-mount product path. Casting/club-mount is
    # gated under casting_pathology (120 cm / 50 ms) — including it in the
    # citeable mean was an honesty bug (25% of cases are distal-mount).
    pos_src = (
        "consumer_wrist"
        if _mean(cross, "e2e", "consumer_wrist", "position_cm") is not None
        else "consumer"
    )
    pos_budget = float(scirep_budgets.PRODUCT_POSITION_CM)
    if e2e_pos is not None and e2e_pos > pos_budget:
        violations.append(
            f"cross_multibody position MAE {e2e_pos:.1f} cm exceeds {pos_budget:.0f} cm "
            f"beyond-consumer budget ({pos_src})"
        )
    elif e2e_pos is not None:
        notes.append(
            f"cross_multibody position MAE {e2e_pos:.2f} cm "
            f"(budget {pos_budget:.0f}, {pos_src})"
        )

    impact = _mean(cross, "events", "impact", "consumer_wrist")
    if impact is None:
        impact = _mean(cross, "events", "impact", "consumer")
    impact_budget = float(scirep_budgets.PRODUCT_IMPACT_MS)
    if impact is not None and impact > impact_budget:
        violations.append(
            f"cross_multibody impact MAE {impact:.1f} ms exceeds {impact_budget:.0f} ms "
            f"beyond-consumer budget"
        )
    elif impact is not None:
        notes.append(
            f"cross_multibody impact MAE {impact:.2f} ms (budget {impact_budget:.0f})"
        )

    e2e_ori = _mean(cross, "e2e", "consumer_wrist", "orientation_deg")
    if e2e_ori is None:
        e2e_ori = _mean(cross, "e2e", "consumer", "orientation_deg")
    ori_budget = float(scirep_budgets.PRODUCT_ORIENTATION_DEG)
    if e2e_ori is not None and e2e_ori > ori_budget:
        violations.append(
            f"cross_multibody orientation MAE {e2e_ori:.1f}° exceeds {ori_budget:.0f}° "
            f"beyond-consumer budget"
        )
    elif e2e_ori is not None:
        notes.append(
            f"cross_multibody orientation MAE {e2e_ori:.2f}° (budget {ori_budget:.0f})"
        )

    # --- aspirational 15 ms / 6° / 12 cm (informational; does not fail CI) ---
    asp_budgets = {
        "impact_ms": float(scirep_budgets.ASPIRATIONAL_IMPACT_MS),
        "orientation_deg": float(scirep_budgets.ASPIRATIONAL_ORIENTATION_DEG),
        "position_cm": float(scirep_budgets.ASPIRATIONAL_POSITION_CM),
    }
    asp_status: dict[str, Any] = {}
    asp_notes: list[str] = []
    asp_fail: list[str] = []
    if impact is not None:
        ok = impact <= asp_budgets["impact_ms"]
        asp_status["impact_ms"] = {
            "value": impact,
            "budget": asp_budgets["impact_ms"],
            "pass": ok,
        }
        (asp_notes if ok else asp_fail).append(
            f"aspirational impact {impact:.2f} ms "
            f"(budget {asp_budgets['impact_ms']:.0f})"
        )
    if e2e_ori is not None:
        ok = e2e_ori <= asp_budgets["orientation_deg"]
        asp_status["orientation_deg"] = {
            "value": e2e_ori,
            "budget": asp_budgets["orientation_deg"],
            "pass": ok,
        }
        (asp_notes if ok else asp_fail).append(
            f"aspirational orientation {e2e_ori:.2f}° "
            f"(budget {asp_budgets['orientation_deg']:.0f})"
        )
    if e2e_pos is not None:
        ok = e2e_pos <= asp_budgets["position_cm"]
        asp_status["position_cm"] = {
            "value": e2e_pos,
            "budget": asp_budgets["position_cm"],
            "pass": ok,
        }
        (asp_notes if ok else asp_fail).append(
            f"aspirational position {e2e_pos:.2f} cm "
            f"(budget {asp_budgets['position_cm']:.0f}, {pos_src})"
        )
    aspirational = {
        "pass": len(asp_fail) == 0 and bool(asp_status),
        "budgets": asp_budgets,
        "status": asp_status,
        "notes": asp_notes,
        "failures": asp_fail,
    }
    if asp_fail:
        notes.append(
            "aspirational 15ms/6deg/12cm not met: " + "; ".join(asp_fail)
        )
    elif asp_status:
        notes.append("aspirational 15ms/6deg/12cm met")

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
            if e_pos is not None and e_pos > 250.0:
                violations.append(
                    f"multisense position {e_pos:.1f} cm exceeds 250 cm "
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
            f"subjects={elite.get('subjects_filter')} "
            f"(eval gate only, not in-product posture library)"
        )
        e_ori = _mean(elite, "orientation_deg")
        e_pos = _mean(elite, "position_cm")
        # Soft ceilings — elite motion is harder; catch adapter/unit regressions.
        if e_ori is not None and e_ori > 22.0:
            violations.append(
                f"multisense elite orientation {e_ori:.1f}° exceeds 22° sanity ceiling"
            )
        if e_pos is not None and e_pos > 250.0:
            violations.append(
                f"multisense elite position {e_pos:.1f} cm exceeds 250 cm sanity ceiling"
            )
        if e_ori is not None:
            notes.append(f"elite orientation {e_ori:.1f}°, position {e_pos}")

    hs = by.get("external_multisense_high_speed", {})
    if hs.get("status") == "ok":
        notes.append(
            f"multisense high-speed stratum n={hs.get('n_swings')} "
            f"(club_speed ≥ {hs.get('club_speed_min_m_s')} m/s)"
        )
        e_ori = _mean(hs, "orientation_deg")
        if e_ori is not None and e_ori > 25.0:
            violations.append(
                f"multisense high-speed orientation {e_ori:.1f}° exceeds 25° ceiling"
            )
    elif hs.get("status") == "unavailable":
        notes.append(f"multisense high-speed unavailable: {hs.get('reason', 'n/a')}")

    cmu = by.get("external_cmu64", {})
    if cmu.get("status") == "ok":
        notes.append(f"external_cmu64 scored n={cmu.get('n_swings')}")
        # Prefer SciRep-style gyro-only ceiling for mocap-synth IMU.
        e_ori = _mean(cmu, "orientation_gyro_only_deg")
        if e_ori is None:
            e_ori = _mean(cmu, "orientation_deg")
        if e_ori is not None and e_ori > 25.0:
            violations.append(
                f"cmu64 gyro-only orientation {e_ori:.1f}° exceeds 25° sanity ceiling"
            )
    elif cmu.get("status") == "unavailable":
        notes.append(f"external_cmu64 unavailable: {cmu.get('reason', 'n/a')}")

    wit = by.get("external_wit_kinnet", {})
    if wit:
        if wit.get("status") == "ok" or wit.get("ready") is True:
            notes.append(
                f"wit_kinnet READY n={wit.get('n_swings', wit.get('n_paired'))} — "
                f"score under SciRep-like MEMS+OMC ceilings"
            )
            e_ori = _mean(wit, "orientation_deg")
            e_pos = _mean(wit, "position_cm")
            if e_ori is not None and e_ori > scirep_budgets.ORIENTATION_DEG_SOFT:
                violations.append(
                    f"wit_kinnet orientation {e_ori:.1f}° exceeds "
                    f"{scirep_budgets.ORIENTATION_DEG_SOFT:.0f}° SciRep soft ceiling"
                )
            if e_pos is not None and e_pos > scirep_budgets.POSITION_CM_WHOLE_SWING * 1.5:
                violations.append(
                    f"wit_kinnet position {e_pos:.1f} cm exceeds "
                    f"{scirep_budgets.POSITION_CM_WHOLE_SWING * 1.5:.0f} cm soft ceiling"
                )
        else:
            notes.append(
                f"wit_kinnet: {wit.get('status', 'unavailable')} — {wit.get('reason', '')}"
            )

    oa = by.get("external_optical_aligned", {})
    if oa.get("status") == "ok":
        notes.append(
            f"optical_aligned (SciRep-protocol twin) n={oa.get('n_swings')} "
            f"@ {oa.get('protocol_fs_hz')} Hz"
        )
        e_ori = _mean(oa, "orientation_deg")
        e_imp = _mean(oa, "impact_ms")
        e_pos = _mean(oa, "position_cm")
        # Product ambition on protocol twin (stricter than soft SciRep orientation).
        if e_ori is not None and e_ori > scirep_budgets.PROTOCOL_TWIN_ORIENTATION_DEG:
            violations.append(
                f"optical_aligned orientation {e_ori:.1f}° exceeds "
                f"{scirep_budgets.PROTOCOL_TWIN_ORIENTATION_DEG:.0f}° protocol-twin ceiling"
            )
        if e_imp is not None and e_imp > scirep_budgets.PROTOCOL_TWIN_IMPACT_MS:
            violations.append(
                f"optical_aligned impact {e_imp:.1f} ms exceeds "
                f"{scirep_budgets.PROTOCOL_TWIN_IMPACT_MS:.0f} ms protocol-twin ceiling"
            )
        if e_pos is not None and e_pos > scirep_budgets.PROTOCOL_TWIN_POSITION_CM:
            violations.append(
                f"optical_aligned position {e_pos:.1f} cm exceeds "
                f"{scirep_budgets.PROTOCOL_TWIN_POSITION_CM:.0f} cm protocol-twin ceiling"
            )
        notes.append(
            f"optical_aligned ori={e_ori} impact={e_imp} pos={e_pos} "
            f"(SciRep ref pos {scirep_budgets.POSITION_CM_WHOLE_SWING} cm)"
        )
    elif oa:
        notes.append(
            f"optical_aligned: {oa.get('status', 'unavailable')} — {oa.get('reason', '')}"
        )

    # --- robust golden tracks (regression ceilings — harder than isomorphic,
    # looser than citeable cross_multibody consumer product gates) ---
    for track, impact_budget, pos_budget_t, ori_budget_t in (
        ("pro_regime", 40.0, 35.0, 40.0),
        ("casting_pathology", 50.0, 120.0, 40.0),
        ("fs_stress", 150.0, 40.0, 20.0),
        ("lefty_mirror", 300.0, 35.0, 15.0),
    ):
        tr = by.get(track, {})
        if not tr or tr.get("empty"):
            continue
        # Prefer e2e consumer; fall back to events/traj
        imp = _mean(tr, "e2e", "consumer", "impact_ms")
        if imp is None:
            imp = _mean(tr, "events", "impact", "consumer")
        pos = _mean(tr, "e2e", "consumer", "position_cm")
        ori = _mean(tr, "e2e", "consumer", "orientation_deg")
        if imp is not None and imp > impact_budget:
            violations.append(
                f"{track} impact MAE {imp:.1f} ms exceeds {impact_budget:.0f} ms budget"
            )
        if pos is not None and pos > pos_budget_t:
            violations.append(
                f"{track} position MAE {pos:.1f} cm exceeds {pos_budget_t:.0f} cm budget"
            )
        if ori is not None and ori > ori_budget_t:
            violations.append(
                f"{track} orientation MAE {ori:.1f}° exceeds {ori_budget_t:.0f}° budget"
            )
        if imp is not None or pos is not None or ori is not None:
            notes.append(
                f"{track}: ori={ori}, impact={imp}, pos={pos} "
                f"(budgets {ori_budget_t}/{impact_budget}/{pos_budget_t})"
            )

    clip = by.get("clip_stress", {})
    if clip and not clip.get("empty"):
        # Clip stress must remain runnable (finite e2e); budgets are softer.
        ori = _mean(clip, "e2e", "consumer_clip", "orientation_deg")
        if ori is None:
            # error_label is consumer_clip — also try nested keys
            e2e = clip.get("e2e", {})
            for k, row in e2e.items():
                if isinstance(row, dict) and "orientation_deg" in row:
                    ori = _mean(row, "orientation_deg")
                    break
        if ori is not None and ori > 25.0:
            violations.append(
                f"clip_stress orientation {ori:.1f}° exceeds 25° soft ceiling"
            )
        else:
            notes.append(f"clip_stress orientation {ori}")

    # --- holdout seal ---
    hold = payload.get("holdout", {})
    if hold.get("enabled") and hold.get("mismatches"):
        violations.extend([f"holdout: {m}" for m in hold["mismatches"]])

    return {
        "pass": len(violations) == 0,
        "violations": violations,
        "notes": notes,
        "aspirational": aspirational,
    }
