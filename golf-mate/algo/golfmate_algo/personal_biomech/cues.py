"""Restrained practice cues derived only from measurable personal deltas.

Cue map tuples are ``(high_error_cue, low_error_cue)`` where high means
``observed > personal baseline``. Directions follow physical metric semantics:

* ``tempo_s`` — duration Address→Impact. Higher = slower swing → speed up.
* ``rhythm`` — backswing/downswing. Higher = long backswing vs downswing →
  smooth transition; lower = rushed → lengthen backswing.
* ``peak_omega_to_impact_s`` — peak-ω lead time before impact. Higher = early
  release/casting → delay release; lower → release earlier.
* ``peak_omega_rad_s`` — peak rate. Higher → ease; lower → build.
* ``plane_angle_deg`` — larger = steeper plane → flatten; smaller → steepen.
"""

from __future__ import annotations

from enum import Enum


class PracticeCue(str, Enum):
    """Measurable, restrained cues — never invent face/path feel language."""

    HOLD_CURRENT = "hold_current"
    TEMPO_SLOW_DOWN = "tempo_slow_down"
    TEMPO_SPEED_UP = "tempo_speed_up"
    RHYTHM_SMOOTH_TRANSITION = "rhythm_smooth_transition"
    RHYTHM_LENGTHEN_BACKSWING = "rhythm_lengthen_backswing"
    RELEASE_DELAY = "release_delay"
    RELEASE_EARLIER = "release_earlier"
    PEAK_OMEGA_BUILD = "peak_omega_build"
    PEAK_OMEGA_EASE = "peak_omega_ease"
    PLANE_FLATTEN = "plane_flatten"
    PLANE_STEEPEN = "plane_steepen"
    PATH_RADIUS_STABLE = "path_radius_stable"
    HAND_SPEED_MATCH = "hand_speed_match"
    ABSTAIN = "abstain"


# Metric -> (cue when observed > baseline, cue when observed < baseline).
_CUE_MAP: dict[str, tuple[PracticeCue, PracticeCue]] = {
    # Duration: longer tempo_s ⇒ slower ⇒ speed up; shorter ⇒ slow down.
    "tempo_s": (PracticeCue.TEMPO_SPEED_UP, PracticeCue.TEMPO_SLOW_DOWN),
    "rhythm": (PracticeCue.RHYTHM_SMOOTH_TRANSITION, PracticeCue.RHYTHM_LENGTHEN_BACKSWING),
    "peak_omega_to_impact_s": (PracticeCue.RELEASE_DELAY, PracticeCue.RELEASE_EARLIER),
    "peak_omega_rad_s": (PracticeCue.PEAK_OMEGA_EASE, PracticeCue.PEAK_OMEGA_BUILD),
    "plane_angle_deg": (PracticeCue.PLANE_FLATTEN, PracticeCue.PLANE_STEEPEN),
    "hand_speed_peak_m_s": (PracticeCue.HAND_SPEED_MATCH, PracticeCue.HAND_SPEED_MATCH),
    "trajectory_radius_m": (PracticeCue.PATH_RADIUS_STABLE, PracticeCue.PATH_RADIUS_STABLE),
}


def cue_for_metric(
    metric: str,
    *,
    signed_error: float | None,
    in_window: bool | None,
) -> PracticeCue:
    """Map signed personal error to a restrained cue enum.

    ``correction_direction`` (elsewhere) remains ``-sign(signed_error)``.
    This cue is the coaching language for that correction.
    """
    if in_window is True:
        return PracticeCue.HOLD_CURRENT
    if signed_error is None or metric not in _CUE_MAP:
        return PracticeCue.ABSTAIN
    high_cue, low_cue = _CUE_MAP[metric]
    if signed_error > 0:
        return high_cue
    if signed_error < 0:
        return low_cue
    return PracticeCue.HOLD_CURRENT
