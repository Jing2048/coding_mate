"""Rule-based coaching diagnostics with explicit proxy labeling."""

from __future__ import annotations

from golfmate_algo.types import DiagnosticFinding, WristFeatures


def diagnose(features: WristFeatures) -> list[DiagnosticFinding]:
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
    # Horizontal plane → normal vertical → angle 0; vertical plane → angle 90
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

    return findings
