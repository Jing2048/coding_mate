"""Pro-swing analysis report: channels + release + manifold + validity."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.biomechanics.release import ReleaseProfile, estimate_release_profile
from golfmate_algo.biomechanics.wrist_channels import (
    SegmentChannels,
    estimate_segment_channels,
)
from golfmate_algo.model.elite_manifold import ManifoldScore, score_against_manifold
from golfmate_algo.model.phase_normalize import phase_normalize
from golfmate_algo.quality.uncertainty import (
    MetricEstimate,
    MetricKind,
    Validity,
    fuse_confidence,
    release_validity,
    trajectory_validity,
)
from golfmate_algo.types import SwingPhases, SwingReport


@dataclass
class ProSwingReport:
    channels: SegmentChannels
    release: ReleaseProfile
    manifold: ManifoldScore | None
    metrics: list[MetricEstimate]
    phase_durations_s: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel_kind": self.channels.channel_kind,
            "release": {
                "morphology": self.release.morphology,
                "onset_s_to_impact": self.release.release_onset_s_to_impact,
                "peak_twist_rate_rad_s": self.release.peak_twist_rate_rad_s,
                "peak_twist_rate_s_to_impact": self.release.peak_twist_rate_s_to_impact,
                "integrated_twist_top_to_impact_rad": (
                    self.release.integrated_twist_top_to_impact_rad
                ),
                "monotonicity": self.release.twist_monotonicity,
                "confidence": self.release.confidence,
                "is_proxy": True,
            },
            "manifold": None
            if self.manifold is None
            else {
                "pca_score": self.manifold.pca_score,
                "residual": self.manifold.residual,
                "phase_residuals": self.manifold.phase_residuals,
                "confidence": self.manifold.confidence,
                "template_version": self.manifold.template_version,
                "is_proxy": True,
            },
            "phase_durations_s": self.phase_durations_s,
            "metrics": [asdict(m) for m in self.metrics],
            "meta": self.meta,
        }


def build_pro_swing_report(
    report: SwingReport,
    *,
    t: ArrayLike,
    gyro: ArrayLike,
    channel_kind: str = "unknown_segment",
) -> ProSwingReport:
    """Derive the professional analysis layer from a SwingReport + raw gyro."""
    t = np.asarray(t, dtype=np.float64)
    gyro = np.asarray(gyro, dtype=np.float64)
    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.005
    plane_n = None
    # Prefer trajectory-derived plane if residual suggests a usable fit
    if report.meta.get("plane_residual_rms", 1.0) < 0.08:
        # reconstruct approximate normal from positions via SVD quickly
        from golfmate_algo.traj.swing_plane import fit_swing_plane

        a, fin = report.phases.address_idx, report.phases.finish_idx
        plane = fit_swing_plane(report.positions[a : fin + 1])
        plane_n = plane.normal

    channels = estimate_segment_channels(
        report.quats,
        gyro,
        dt,
        address_idx=report.phases.address_idx,
        plane_normal_world=plane_n,
        channel_kind=channel_kind,
    )
    hand_speed = np.linalg.norm(report.velocities, axis=1)
    release = estimate_release_profile(
        t, channels, report.phases, hand_speed=hand_speed
    )

    omega = np.linalg.norm(gyro, axis=1)
    mat = np.column_stack(
        [omega, channels.twist_rate_rad_s, channels.omega_plane_rad_s, channels.twist_rad]
    )
    names = ("omega", "twist_rate", "plane_rate", "twist")
    normed = phase_normalize(t, mat, report.phases, channel_names=names)
    man_score = score_against_manifold(normed)

    traj_v, traj_reasons, traj_conf = trajectory_validity(
        radius_m=float(report.meta.get("radius_m", 0.0)),
        residual_rms=float(report.meta.get("residual_rms_m_s2", 0.0)),
        rank=float(report.meta.get("rank", 0.0)),
        fallback=float(report.meta.get("fallback", 0.0)),
    )
    rel_v, rel_reasons, rel_conf = release_validity(
        impact_mode=str(report.meta.get("impact_mode", "collision")),
        release_confidence=release.confidence,
        peak_omega=float(report.features.peak_omega_rad_s),
    )

    metrics = [
        MetricEstimate(
            name="release_onset_s_to_impact",
            value=release.release_onset_s_to_impact,
            units="s",
            kind=MetricKind.PROXY,
            confidence=rel_conf,
            validity=rel_v,
            reasons=rel_reasons,
        ),
        MetricEstimate(
            name="segment_twist_integral_rad",
            value=release.integrated_twist_top_to_impact_rad,
            units="rad",
            kind=MetricKind.DERIVED,
            confidence=fuse_confidence(rel_conf, traj_conf),
            validity=rel_v if rel_v != Validity.OK else traj_v,
            reasons=list(dict.fromkeys(rel_reasons + traj_reasons)),
        ),
        MetricEstimate(
            name="trajectory_radius_m",
            value=float(report.meta.get("radius_m", float("nan"))),
            units="m",
            kind=MetricKind.DERIVED,
            confidence=traj_conf,
            validity=traj_v,
            reasons=traj_reasons,
        ),
    ]
    if man_score is not None:
        metrics.append(
            MetricEstimate(
                name="pro_manifold_pca_score",
                value=man_score.pca_score,
                units="1",
                kind=MetricKind.PROXY,
                confidence=man_score.confidence,
                validity=Validity.OK if man_score.confidence > 0.3 else Validity.DEGRADED,
                reasons=[],
            )
        )

    return ProSwingReport(
        channels=channels,
        release=release,
        manifold=man_score,
        metrics=metrics,
        phase_durations_s=dict(normed.phase_durations_s),
        meta={
            "phase_normalize_valid": float(normed.validity),
            "channel_kind": channel_kind,
            "is_proxy": True,
        },
    )
