"""Release morphology proxies from segment channels (Top → post-impact).

These describe *segment* axial-rotation / plane-rate release timing — not clubface
closure, shaft lean, or anatomical wrist flexion (those need extra rigid bodies).

Inspired by HackMotion release profiles and Cheetham kinematic-sequence timing,
adapted to a single distal IMU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.biomechanics.wrist_channels import SegmentChannels
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]


@dataclass
class ReleaseProfile:
    release_onset_s_to_impact: float
    peak_twist_rate_rad_s: float
    peak_twist_rate_s_to_impact: float
    peak_plane_rate_rad_s: float
    peak_plane_rate_s_to_impact: float
    integrated_twist_top_to_impact_rad: float
    release_duration_s: float
    twist_monotonicity: float  # 1 = no reversals in downswing twist rate sign
    hand_speed_coord: float  # corr(plane_rate, |v|) in downswing, or nan
    morphology: str  # early | gradual | late | abrupt | unclear
    confidence: float
    is_proxy: bool = True
    extras: dict[str, float] = field(default_factory=dict)


def _morphology_label(
    onset_to_imp: float,
    duration: float,
    mono: float,
) -> str:
    if not np.isfinite(onset_to_imp):
        return "unclear"
    if onset_to_imp > 0.12 and duration > 0.10:
        return "early"
    if onset_to_imp > 0.06 and duration > 0.06:
        return "gradual"
    if onset_to_imp < 0.03 and duration < 0.05:
        return "abrupt"
    if onset_to_imp < 0.05:
        return "late"
    return "gradual"


def estimate_release_profile(
    t: ArrayLike,
    channels: SegmentChannels,
    phases: SwingPhases,
    *,
    hand_speed: ArrayLike | None = None,
) -> ReleaseProfile:
    """Estimate release morphology between Top and shortly after Impact."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    top, imp, fin = phases.top_idx, phases.impact_idx, phases.finish_idx
    n = t.shape[0]
    top = int(np.clip(top, 0, n - 2))
    imp = int(np.clip(imp, top + 1, n - 1))
    fin = int(np.clip(fin, imp, n - 1))
    post = min(fin, imp + max(3, (fin - imp) // 4))

    twist_rate = channels.twist_rate_rad_s
    plane_rate = channels.omega_plane_rad_s
    down = slice(top, imp + 1)

    # Soft release onset: first sample where twist-rate and plane-rate both rise.
    thr_tw = 0.35 * float(np.max(np.abs(twist_rate[down])) + 1e-9)
    thr_pl = 0.35 * float(np.max(plane_rate[down]) + 1e-9)
    onset_idx = top
    found = False
    for i in range(top, imp):
        if abs(twist_rate[i]) > thr_tw and plane_rate[i] > thr_pl:
            # require rising plane rate
            if i + 1 < n and plane_rate[i + 1] >= plane_rate[i]:
                onset_idx = i
                found = True
                break
    if not found:
        # fallback: max |twist_rate| ascent
        onset_idx = top + int(np.argmax(np.abs(twist_rate[down])))

    onset_to_imp = float(t[imp] - t[onset_idx])
    duration = float(t[imp] - t[onset_idx])

    # Peak rates in top→post window
    win = slice(top, post + 1)
    i_tw = top + int(np.argmax(np.abs(twist_rate[win])))
    i_pl = top + int(np.argmax(plane_rate[win]))
    peak_tw = float(twist_rate[i_tw])
    peak_pl = float(plane_rate[i_pl])
    peak_tw_to_imp = float(t[imp] - t[i_tw])
    peak_pl_to_imp = float(t[imp] - t[i_pl])

    integ = float(channels.twist_rad[imp] - channels.twist_rad[top])

    # Monotonicity of twist-rate sign in late downswing
    late = twist_rate[onset_idx : imp + 1]
    if late.size >= 3:
        sgn = np.sign(late)
        sgn = sgn[sgn != 0]
        flips = float(np.sum(sgn[1:] * sgn[:-1] < 0)) if sgn.size > 1 else 0.0
        mono = float(np.clip(1.0 - flips / max(sgn.size - 1, 1), 0.0, 1.0))
    else:
        mono = 0.5

    coord = float("nan")
    if hand_speed is not None:
        hs = np.asarray(hand_speed, dtype=np.float64).reshape(-1)
        seg_pl = plane_rate[down]
        seg_hs = hs[down]
        if seg_pl.size > 4 and np.std(seg_pl) > 1e-9 and np.std(seg_hs) > 1e-9:
            coord = float(np.corrcoef(seg_pl, seg_hs)[0, 1])

    morph = _morphology_label(onset_to_imp, duration, mono)
    conf = float(
        np.clip(
            0.35
            + 0.25 * mono
            + (0.2 if found else 0.0)
            + (0.15 if np.isfinite(coord) and coord > 0.3 else 0.0),
            0.1,
            0.9,
        )
    )
    return ReleaseProfile(
        release_onset_s_to_impact=onset_to_imp,
        peak_twist_rate_rad_s=peak_tw,
        peak_twist_rate_s_to_impact=peak_tw_to_imp,
        peak_plane_rate_rad_s=peak_pl,
        peak_plane_rate_s_to_impact=peak_pl_to_imp,
        integrated_twist_top_to_impact_rad=integ,
        release_duration_s=duration,
        twist_monotonicity=mono,
        hand_speed_coord=coord,
        morphology=morph,
        confidence=conf,
        is_proxy=True,
        extras={
            "onset_found": float(found),
            "onset_idx": float(onset_idx),
            "peak_twist_idx": float(i_tw),
            "peak_plane_idx": float(i_pl),
        },
    )
