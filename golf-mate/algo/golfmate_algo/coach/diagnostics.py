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

    # High-order inferred wrist / clubface / sequence (PCR latent body)
    if high_order and high_order.get("kind") == "inferred":
        conf = float(high_order.get("confidence", 0.0))
        wrist = high_order.get("wrist") or {}
        club = high_order.get("club") or {}
        body = high_order.get("body") or {}
        if conf >= 0.35:
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
                            "confidence": conf,
                        },
                        is_proxy=False,
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
                            "confidence": conf,
                        },
                        is_proxy=False,
                    )
                )

            face_state = str(club.get("face_open_closed", "square"))
            face_deg = float(club.get("face_impact_deg", float("nan")))
            if face_state == "open" and conf >= 0.4:
                findings.append(
                    DiagnosticFinding(
                        code="clubface_open_impact",
                        severity="warn",
                        message=(
                            "Inferred clubface is open at impact "
                            "(single-IMU PCR; not a launch-monitor reading)."
                        ),
                        evidence={"face_impact_deg": face_deg, "confidence": conf},
                        is_proxy=False,
                    )
                )
            elif face_state == "closed" and conf >= 0.4:
                findings.append(
                    DiagnosticFinding(
                        code="clubface_closed_impact",
                        severity="info",
                        message=(
                            "Inferred clubface is closed at impact "
                            "(single-IMU PCR; not a launch-monitor reading)."
                        ),
                        evidence={"face_impact_deg": face_deg, "confidence": conf},
                        is_proxy=False,
                    )
                )

            if body.get("sequence_order_ok") is False and conf >= 0.35:
                findings.append(
                    DiagnosticFinding(
                        code="kinematic_sequence_out_of_order",
                        severity="warn",
                        message=(
                            "Inferred pelvis→torso→arm→club peak order looks "
                            "out of sequence (PCR latent model)."
                        ),
                        evidence={
                            "pelvis_peak_to_impact_s": body.get("pelvis_peak_to_impact_s"),
                            "club_peak_to_impact_s": body.get("club_peak_to_impact_s"),
                            "confidence": conf,
                        },
                        is_proxy=False,
                    )
                )

    return findings
