"""Rule-based coaching diagnostics with explicit proxy labeling."""

from __future__ import annotations

from typing import Any

import numpy as np

from golfmate_algo.types import DiagnosticFinding, WristFeatures


def diagnose(
    features: WristFeatures,
    *,
    pro: dict[str, Any] | None = None,
    high_order: dict[str, Any] | None = None,
) -> list[DiagnosticFinding]:
    findings: list[DiagnosticFinding] = []

    # Rhythm: classic ~3:1 backswing:downswing band
    if features.rhythm < 1.8:
        findings.append(
            DiagnosticFinding(
                code="rhythm_too_fast_backswing",
                severity="warn",
                message="Backswing/downswing rhythm is low (<1.8); often rushed transition.",
                evidence={"rhythm": features.rhythm},
                is_proxy=True,
            )
        )
    elif features.rhythm > 4.5:
        findings.append(
            DiagnosticFinding(
                code="rhythm_too_slow_backswing",
                severity="info",
                message="Rhythm is high (>4.5); backswing may be overly long vs downswing.",
                evidence={"rhythm": features.rhythm},
                is_proxy=True,
            )
        )
    else:
        findings.append(
            DiagnosticFinding(
                code="rhythm_ok",
                severity="info",
                message="Rhythm within a typical amateur-to-tour band (~2–4).",
                evidence={"rhythm": features.rhythm},
                is_proxy=True,
            )
        )

    # Casting proxy: peak ω arrives too early before impact
    if features.peak_omega_to_impact_s > 0.08:
        findings.append(
            DiagnosticFinding(
                code="casting_proxy",
                severity="warn",
                message=(
                    "Peak wrist angular rate occurs early relative to impact "
                    "(casting / early release proxy)."
                ),
                evidence={
                    "peak_omega_to_impact_s": features.peak_omega_to_impact_s,
                    "peak_omega_rad_s": features.peak_omega_rad_s,
                },
                is_proxy=True,
            )
        )
    elif features.peak_omega_to_impact_s < -0.02:
        findings.append(
            DiagnosticFinding(
                code="late_peak_omega",
                severity="info",
                message="Peak ω after impact index — check phase detection or sensor saturation.",
                evidence={"peak_omega_to_impact_s": features.peak_omega_to_impact_s},
                is_proxy=True,
            )
        )
    else:
        findings.append(
            DiagnosticFinding(
                code="release_timing_ok",
                severity="info",
                message="Peak ω timing near impact looks reasonable for this proxy.",
                evidence={"peak_omega_to_impact_s": features.peak_omega_to_impact_s},
                is_proxy=True,
            )
        )

    # Steep / flat plane proxy via plane_angle_deg (angle of normal to vertical)
    pa = features.plane_angle_deg
    if pa < 35.0:
        findings.append(
            DiagnosticFinding(
                code="plane_flat_proxy",
                severity="info",
                message="Estimated swing plane is relatively flat (proxy).",
                evidence={"plane_angle_deg": pa},
                is_proxy=True,
            )
        )
    elif pa > 70.0:
        findings.append(
            DiagnosticFinding(
                code="plane_steep_proxy",
                severity="info",
                message="Estimated swing plane is relatively steep (proxy).",
                evidence={"plane_angle_deg": pa},
                is_proxy=True,
            )
        )

    if features.tempo_s < 0.6:
        findings.append(
            DiagnosticFinding(
                code="tempo_very_fast",
                severity="warn",
                message="Overall tempo Address→Impact is very short.",
                evidence={"tempo_s": features.tempo_s},
                is_proxy=True,
            )
        )

    # Pro-swing release morphology (segment twist proxy — not clubface)
    if pro and isinstance(pro.get("release"), dict):
        rel = pro["release"]
        morph = str(rel.get("morphology", "unclear"))
        onset = float(rel.get("onset_s_to_impact", float("nan")))
        conf = float(rel.get("confidence", 0.0))
        if morph == "early" and conf >= 0.35:
            findings.append(
                DiagnosticFinding(
                    code="release_early_proxy",
                    severity="warn",
                    message=(
                        "Segment twist release onset is early vs impact "
                        "(early-release morphology proxy; not clubface)."
                    ),
                    evidence={"onset_s_to_impact": onset, "confidence": conf},
                    is_proxy=True,
                )
            )
        elif morph == "abrupt" and conf >= 0.35:
            findings.append(
                DiagnosticFinding(
                    code="release_abrupt_proxy",
                    severity="info",
                    message="Segment twist release looks abrupt near impact (proxy).",
                    evidence={"onset_s_to_impact": onset, "confidence": conf},
                    is_proxy=True,
                )
            )
        elif morph in {"gradual", "late"} and conf >= 0.35:
            findings.append(
                DiagnosticFinding(
                    code="release_morphology_ok",
                    severity="info",
                    message=f"Release morphology proxy: {morph}.",
                    evidence={"onset_s_to_impact": onset, "confidence": conf},
                    is_proxy=True,
                )
            )

        man = pro.get("manifold")
        if isinstance(man, dict) and man.get("pca_score") is not None:
            score = float(man["pca_score"])
            if score > 3.0:
                findings.append(
                    DiagnosticFinding(
                        code="pro_manifold_outlier",
                        severity="info",
                        message=(
                            "Waveform shape is far from the professional reference "
                            "manifold (distributional; not a single correct posture)."
                        ),
                        evidence={
                            "pca_score": score,
                            "residual": float(man.get("residual", float("nan"))),
                        },
                        is_proxy=True,
                    )
                )

    # High-order inferred wrist / clubface / sequence (PCR latent body).
    # These are NEVER measured: keep is_proxy=True and kind="inferred".
    # Findings require the exact scalar(s) used to be non-abstained.
    if high_order and high_order.get("kind") == "inferred":
        wrist = high_order.get("wrist") or {}
        club = high_order.get("club") or {}
        body = high_order.get("body") or {}

        def _scalar_gate(
            section: dict[str, Any],
            metric_alias: str,
            fallback_conf: float,
            *,
            min_conf: float = 0.35,
        ) -> tuple[bool, float, float]:
            """Gate on section.metrics[alias] when present; else head validity."""
            metrics = section.get("metrics") if isinstance(section.get("metrics"), dict) else {}
            entry = metrics.get(metric_alias) if isinstance(metrics, dict) else None
            if isinstance(entry, dict) and "validity" in entry:
                validity = str(entry.get("validity", "abstain"))
                if validity == "abstain":
                    return False, 0.0, float("nan")
                conf = float(entry.get("confidence", fallback_conf))
                residual = float(
                    entry.get("residual", section.get("residual", high_order.get("residual", float("nan"))))
                )
                return conf >= min_conf, conf, residual
            # Legacy path without metrics mapping: head-level gate.
            validity = str(section.get("validity", high_order.get("validity", "degraded")))
            if validity == "abstain":
                return False, 0.0, float("nan")
            conf = float(section.get("confidence", fallback_conf))
            residual = float(section.get("residual", high_order.get("residual", float("nan"))))
            return conf >= min_conf, conf, residual

        global_conf = float(high_order.get("confidence", 0.0))
        fe_ok, fe_conf, fe_resid = _scalar_gate(wrist, "fe_impact", global_conf)
        delta_ok, delta_conf, delta_resid = _scalar_gate(
            wrist, "fe_delta_address_to_impact", global_conf
        )
        if fe_ok and delta_ok:
            wrist_conf = min(fe_conf, delta_conf)
            wrist_resid = (
                fe_resid if np.isfinite(fe_resid) else delta_resid
            )
            fe_imp = float(wrist.get("fe_impact_deg", float("nan")))
            fe_d = float(wrist.get("fe_delta_address_to_impact_deg", float("nan")))
            if np.isfinite(fe_d) and fe_d < -5.0:
                findings.append(
                    DiagnosticFinding(
                        code="wrist_extends_into_impact",
                        severity="warn",
                        message=(
                            "Inferred lead wrist adds extension into impact "
                            "(cupping tendency; PCR latent model)."
                        ),
                        evidence={
                            "fe_impact_deg": fe_imp,
                            "fe_delta_deg": fe_d,
                            "confidence": wrist_conf,
                            "residual": wrist_resid,
                            "head": "wrist",
                            "metrics": ["fe_impact", "fe_delta_address_to_impact"],
                        },
                        is_proxy=True,
                        kind="inferred",
                    )
                )
            elif np.isfinite(fe_d) and fe_d > 8.0:
                findings.append(
                    DiagnosticFinding(
                        code="wrist_bows_into_impact",
                        severity="info",
                        message=(
                            "Inferred lead wrist flexes/bows into impact "
                            "(PCR latent model)."
                        ),
                        evidence={
                            "fe_impact_deg": fe_imp,
                            "fe_delta_deg": fe_d,
                            "confidence": wrist_conf,
                            "residual": wrist_resid,
                            "head": "wrist",
                            "metrics": ["fe_impact", "fe_delta_address_to_impact"],
                        },
                        is_proxy=True,
                        kind="inferred",
                    )
                )

        face_ok, club_conf, club_resid = _scalar_gate(
            club, "face_impact", global_conf, min_conf=0.4
        )
        if face_ok:
            face_state = str(club.get("face_open_closed", "square"))
            face_deg = float(club.get("face_impact_deg", float("nan")))
            if face_state == "open":
                findings.append(
                    DiagnosticFinding(
                        code="clubface_open_impact",
                        severity="warn",
                        message=(
                            "Inferred clubface is open at impact "
                            "(single-IMU PCR; not a launch-monitor reading)."
                        ),
                        evidence={
                            "face_impact_deg": face_deg,
                            "confidence": club_conf,
                            "residual": club_resid,
                            "head": "club",
                            "metrics": ["face_impact"],
                        },
                        is_proxy=True,
                        kind="inferred",
                    )
                )
            elif face_state == "closed":
                findings.append(
                    DiagnosticFinding(
                        code="clubface_closed_impact",
                        severity="info",
                        message=(
                            "Inferred clubface is closed at impact "
                            "(single-IMU PCR; not a launch-monitor reading)."
                        ),
                        evidence={
                            "face_impact_deg": face_deg,
                            "confidence": club_conf,
                            "residual": club_resid,
                            "head": "club",
                            "metrics": ["face_impact"],
                        },
                        is_proxy=True,
                        kind="inferred",
                    )
                )

        # Sequence finding uses body peak timings; require body head + x_factor
        # scalar (only body scalar with MAE budget) non-abstained.
        body_head_ok = str(body.get("validity", high_order.get("validity", "degraded"))) != "abstain"
        xf_ok, body_conf, body_resid = _scalar_gate(body, "x_factor_top", global_conf)
        if (
            body_head_ok
            and xf_ok
            and body.get("sequence_order_ok") is False
            and body_conf >= 0.35
        ):
            findings.append(
                DiagnosticFinding(
                    code="kinematic_sequence_out_of_order",
                    severity="warn",
                    message=(
                        "Inferred pelvis→torso→arm→club peak order looks "
                        "out of sequence (PCR latent model)."
                    ),
                    evidence={
                        "pelvis_peak_to_impact_s": float(
                            body.get("pelvis_peak_to_impact_s", float("nan"))
                        ),
                        "club_peak_to_impact_s": float(
                            body.get("club_peak_to_impact_s", float("nan"))
                        ),
                        "confidence": body_conf,
                        "residual": body_resid,
                        "head": "body",
                        "metrics": ["x_factor_top"],
                    },
                    is_proxy=True,
                    kind="inferred",
                )
            )

    return findings
