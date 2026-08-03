"""Physics-grounded swing phase detection with adaptive scales.

Design rationale
----------------
Threshold rules on |omega| are brittle because the absolute rate scale varies by
player, club and sensor mounting. This detector instead anchors each event to a
*definition that is invariant to those scales*:

- **Impact** is the largest band-passed accelerometer transient. The strike is a
  broadband mechanical shock, which is why high-rate accelerometer streams are
  the standard cue for strike timing.
- **Top of backswing** is the sign change of the angular rate projected on the
  dominant swing axis. At the top the motion physically reverses, so the signed
  rate crosses zero regardless of magnitude.
- **Address / Finish** are found by hysteresis against thresholds derived from
  the signal's own peak (a fixed fraction of peak rate), not absolute constants.

A segmental dynamic program is retained as a fallback for degraded signals where
the zero crossing is ambiguous (e.g. clipped gyro), so the detector degrades
gracefully rather than failing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]


@dataclass
class SegmentationDiagnostics:
    dominant_axis: ArrayF
    signed_rate: ArrayF
    omega: ArrayF
    impact_score: ArrayF
    method: str
    quality: dict[str, float]
    impact_mode: str = "collision"  # collision | kinematic_proxy | unavailable
    impact_confidence: float = 1.0


def _moving_average(x: ArrayF, win: int) -> ArrayF:
    if win <= 1:
        return x
    k = np.ones(win, dtype=np.float64) / win
    pad = win // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    return np.convolve(xp, k, mode="same")[pad : pad + x.shape[0]]


def _impact_transient(acc_mag: ArrayF, fs: float) -> ArrayF:
    """Envelope of the high-frequency accelerometer content.

    Ball strike is a broadband mechanical shock, whereas swing dynamics
    (centripetal and tangential terms) are smooth and low frequency. A high-pass
    at a fraction of Nyquist therefore separates the strike from the much larger
    but slow centripetal bump, which simple envelope subtraction cannot do.
    """
    nyq = 0.5 * fs
    cutoff = min(40.0, 0.4 * nyq)
    if cutoff <= 0 or acc_mag.shape[0] < 30:
        return np.abs(acc_mag - _moving_average(acc_mag, 9))
    try:
        from scipy.signal import butter, filtfilt

        b, a = butter(2, cutoff / nyq, btype="highpass")
        hp = filtfilt(b, a, acc_mag, method="gust")
    except Exception:
        hp = acc_mag - _moving_average(acc_mag, max(5, int(0.05 * fs)))
    return _moving_average(np.abs(hp), max(3, int(0.006 * fs)))


def _dominant_rotation_axis(gyro: ArrayF, omega: ArrayF) -> ArrayF:
    """Principal axis of the angular-velocity cloud, weighted by speed."""
    w = gyro * omega[:, None]
    _, _, vh = np.linalg.svd(w - w.mean(axis=0), full_matrices=False)
    axis = vh[0]
    return axis / (np.linalg.norm(axis) + 1e-12)


def _hysteresis_backward(omega: ArrayF, start: int, hi: float, lo: float) -> int:
    """Walk back from ``start`` to the last index that is quiet below ``lo``."""
    i = start
    while i > 0 and omega[i] > hi:
        i -= 1
    while i > 0 and omega[i] > lo:
        i -= 1
    return max(0, i)


def _hysteresis_forward(omega: ArrayF, start: int, hi: float, lo: float) -> int:
    n = omega.shape[0]
    i = start
    while i < n - 1 and omega[i] > hi:
        i += 1
    while i < n - 1 and omega[i] > lo:
        i += 1
    return min(n - 1, i)


def detect_phases_segmental(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    *,
    quiet_frac_hi: float = 0.10,
    quiet_frac_lo: float = 0.04,
    min_backswing_s: float = 0.15,
    min_downswing_s: float = 0.05,
    return_diagnostics: bool = False,
) -> SwingPhases | tuple[SwingPhases, SegmentationDiagnostics]:
    """Detect Address / Top / Impact / Finish."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = t.shape[0]
    if n < 20:
        raise ValueError("need at least 20 samples")
    dt = float(np.median(np.diff(t)))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("non-monotonic timestamps")
    fs = 1.0 / dt

    sm = max(3, int(0.015 * fs))
    omega_raw = np.linalg.norm(gyro, axis=1)
    omega = _moving_average(omega_raw, sm)
    axis = _dominant_rotation_axis(gyro, omega)
    signed = _moving_average(gyro @ axis, sm)

    impact_score = _impact_transient(np.linalg.norm(accel, axis=1), fs)

    peak_omega = float(np.max(omega))
    if peak_omega <= 1e-6:
        raise ValueError("no motion detected")
    hi = quiet_frac_hi * peak_omega
    lo = quiet_frac_lo * peak_omega

    # --- Motion span: first/last excursion above the adaptive high threshold
    active = omega > hi
    if not np.any(active):
        raise ValueError("no motion above adaptive threshold")
    motion_start = int(np.argmax(active))
    motion_end = n - 1 - int(np.argmax(active[::-1]))

    # --- Impact: collision shock when SNR allows; else kinematic proxy.
    # Collision = broadband mechanical transient (club–ball). Mocap-derived /
    # low-ODR streams lack that shock — do NOT silently rename peak-ω as impact
    # without labelling the semantic change.
    #
    # SciRep / casting-robust selection (extreme-algo):
    # 1) Coarse top from signed-rate zero-crossing so we never pick backswing
    #    release spikes (club-mount casting creates early HF energy).
    # 2) Among significant peaks *after* top, prefer the latest (ball strike
    #    is typically the last large transient in the downswing window).
    peak_idx = int(np.argmax(omega))
    down_sign = np.sign(signed[peak_idx]) if signed[peak_idx] != 0 else 1.0
    coarse_top = -1
    for i in range(min(peak_idx, n - 1), 0, -1):
        if signed[i] * down_sign > 0 and signed[i - 1] * down_sign <= 0:
            coarse_top = i - 1
            break
    if coarse_top < 0:
        coarse_top = int(np.argmin(np.abs(signed[: max(1, peak_idx)])))

    search_lo = max(0, motion_start - int(0.05 * fs))
    search_hi = min(n - 1, motion_end + int(0.10 * fs))
    # Gate collision search to post-top (downswing / early follow-through).
    search_lo = max(search_lo, int(coarse_top))
    seg = impact_score[search_lo : search_hi + 1]
    method = "transient"
    impact_mode = "collision"
    impact_confidence = 1.0
    noise_floor = float(np.median(impact_score)) + 1e-9
    snr = float(np.max(seg) / noise_floor) if seg.size else 0.0
    # Need usable bandwidth for a strike transient (~>80 Hz Nyquist ⇒ fs≳160).
    collision_feasible = fs >= 120.0 and snr > 4.0
    impact_idx = -1
    if seg.size and collision_feasible:
        # Prefer collision peaks near peak-|ω| (golf impact ≈ max rate + shock).
        # Casting: peak-|ω| is early (release) while ball strike is a later HF
        # peak — accept latest significant peak at/after peak-|ω|.
        # Clean high-ODR synth without ball shock: no peak near/after peak-|ω|
        # clears thr → kinematic proxy (avoid latching top-transition HF).
        peak_in = float(np.max(seg))
        peak_omega_rel = int(np.clip(peak_idx - search_lo, 0, max(0, seg.size - 1)))
        # Casting: early release HF can dominate seg max and raise thr above the
        # real strike. Threshold post-peak candidates against the post-peak max.
        peak_after = float(np.max(seg[peak_omega_rel:])) if peak_omega_rel < seg.size else peak_in
        thr_pre = max(3.0 * noise_floor, 0.45 * peak_in)
        thr_post = max(3.0 * noise_floor, 0.30 * peak_after)
        cand_pre: list[int] = []
        cand_post: list[int] = []
        for j in range(1, seg.size - 1):
            if not (seg[j] >= seg[j - 1] and seg[j] >= seg[j + 1]):
                continue
            if j < peak_omega_rel - max(1, int(0.02 * fs)):
                if seg[j] >= thr_pre:
                    cand_pre.append(j)
            else:
                if seg[j] >= thr_post:
                    cand_post.append(j)
        win = max(1, int(0.12 * fs))
        near = [j for j in cand_post if abs(j - peak_omega_rel) <= win]
        after = list(cand_post)
        soft_thr = max(3.0 * noise_floor, 0.15 * peak_after)
        lo_w = max(0, peak_omega_rel - win)
        hi_w = min(seg.size, peak_omega_rel + win + 1)
        win_seg = seg[lo_w:hi_w]
        win_argmax = lo_w + int(np.argmax(win_seg)) if win_seg.size else peak_omega_rel
        if near:
            impact_rel = max(near, key=lambda j: float(seg[j]))
            impact_idx = search_lo + impact_rel
            method = "transient_near_peak_omega"
            impact_confidence = float(np.clip((snr - 4.0) / 8.0, 0.35, 1.0))
        elif after:
            # Prefer strongest post-peak candidate (strike), not merely latest.
            impact_rel = max(after, key=lambda j: float(seg[j]))
            impact_idx = search_lo + impact_rel
            method = "transient_best_after_peak_omega"
            impact_confidence = float(np.clip((snr - 4.0) / 8.0, 0.35, 1.0))
        elif (
            float(seg[win_argmax]) >= soft_thr
            and float(omega[search_lo + win_argmax]) >= 0.25 * peak_omega
        ):
            impact_idx = search_lo + win_argmax
            method = "transient_peak_omega_window"
            impact_confidence = float(np.clip((snr - 4.0) / 8.0, 0.35, 1.0))
        elif cand_pre and not after:
            # No post-peak collision — leave to kinematic proxy.
            pass

    if impact_idx < 0:
        # Kinematic proxy: after the likely top, blend |ω| with |a|.
        # In a real downswing, centripetal |a| and rate both rise toward impact.
        top_guess = int(coarse_top)
        lo_k = max(top_guess + 1, motion_start)
        hi_k = min(n - 1, motion_end + 1)
        if hi_k <= lo_k:
            lo_k, hi_k = motion_start, max(motion_start + 1, motion_end)
        acc_mag = np.linalg.norm(accel, axis=1)
        kin = 0.55 * (omega / (peak_omega + 1e-9)) + 0.45 * (
            acc_mag / (float(np.max(acc_mag)) + 1e-9)
        )
        impact_idx = lo_k + int(np.argmax(kin[lo_k : hi_k + 1]))
        method = "kinematic_proxy"
        impact_mode = "kinematic_proxy"
        impact_confidence = 0.45 if fs < 120.0 else 0.55
        if snr <= 1.5 and peak_omega < 1.0:
            impact_mode = "unavailable"
            impact_confidence = 0.15
            method = "unavailable_low_signal"

    # --- Top: sign reversal of the signed rate before impact
    top_idx = -1
    search_from = min(impact_idx, n - 1)
    for i in range(search_from, 0, -1):
        if signed[i] * down_sign > 0 and signed[i - 1] * down_sign <= 0:
            top_idx = i - 1
            break
    if top_idx < 0:
        upper = max(1, peak_idx)
        top_idx = int(np.argmin(np.abs(signed[:upper])))
        method += "+top_minabs"

    min_ds = max(1, int(min_downswing_s * fs))
    if impact_idx - top_idx < min_ds:
        top_idx = max(1, impact_idx - min_ds)

    # --- Address / Finish (SciRep Kim&Park 2024 kinematic anchors)
    # ADD ≈ last sustained quiet before takeaway. FIN ≈ last sustained quiet
    # in follow-through (early mid-FT dips are common under consumer noise).
    quiet_n = max(2, int(0.04 * fs))
    address_idx = _hysteresis_backward(omega, motion_start, hi, lo)

    # SciRep walk-back from Top: skip top quiet → traverse backswing → pre-swing quiet.
    # Only engage when hysteresis collapsed toward Top (failed takeaway lock).
    i = int(top_idx)
    while i > 0 and omega[i] < hi:
        i -= 1
    while i > 0 and omega[i] >= lo:
        i -= 1
    run = 0
    addr_from_top = i
    for j in range(i, -1, -1):
        if omega[j] < lo:
            run += 1
            if run >= quiet_n:
                addr_from_top = j
                break
        else:
            run = 0
    if top_idx - address_idx < int(0.35 * fs):
        # Hysteresis failed / started mid-backswing — pull toward SciRep quiet.
        address_idx = min(address_idx, addr_from_top)
    address_idx = min(address_idx, max(0, top_idx - 1))
    min_bs = int(min_backswing_s * fs)
    if top_idx - address_idx < min_bs:
        address_idx = max(0, top_idx - min_bs)

    # Finish: SciRep FIN ≈ settling local-min after impact.
    # First sustained quiet (good on clean planar); if that crossing is still
    # shallow vs the address quiet floor, deepen to the ω argmin over the next
    # ~0.5 s (consumer multibody often dips mid-FT before true settle).
    min_ft = impact_idx + max(1, int(0.15 * fs))
    max_ft = impact_idx + max(int(1.20 * fs), quiet_n * 5)
    max_ft = min(n - 1, max_ft)
    min_ft = min(min_ft, max_ft)
    finish_hyst = _hysteresis_forward(omega, max(motion_end, impact_idx), hi, lo)

    a0 = max(0, address_idx - quiet_n * 2)
    addr_floor = float(np.median(omega[a0 : address_idx + 1])) + 1e-9

    run = 0
    onset: int | None = None
    for j in range(min_ft, max_ft + 1):
        if omega[j] < lo:
            run += 1
            if run >= quiet_n:
                onset = j - quiet_n + 1
                break
        else:
            run = 0
    if onset is None:
        seg_ft = omega[min_ft : max_ft + 1]
        fin_cand = min_ft + int(np.argmin(seg_ft)) if seg_ft.size else min_ft
    else:
        fin_cand = int(onset)
        shallow = float(omega[onset]) > max(2.5 * addr_floor, 0.45 * lo)
        if shallow:
            end = min(max_ft, onset + max(1, int(0.50 * fs)))
            deep = onset + int(np.argmin(omega[onset : end + 1]))
            if float(omega[deep]) < 0.5 * float(omega[onset]):
                fin_cand = int(deep)
    # Hysteresis may push later inside the window (avoid early motion_end cutoffs).
    if min_ft <= finish_hyst <= max_ft:
        finish_idx = max(fin_cand, finish_hyst)
    else:
        finish_idx = fin_cand
    finish_idx = int(np.clip(finish_idx, min_ft, max_ft))
    finish_idx = max(finish_idx, min(n - 1, impact_idx + 1))

    top_idx = int(np.clip(top_idx, address_idx + 1, impact_idx - 1))
    impact_idx = int(np.clip(impact_idx, top_idx + 1, max(top_idx + 2, finish_idx - 1)))
    finish_idx = int(np.clip(finish_idx, impact_idx + 1, n - 1))

    phases = SwingPhases(
        address_idx=int(address_idx),
        top_idx=int(top_idx),
        impact_idx=int(impact_idx),
        finish_idx=int(finish_idx),
    )
    phases.validate_order()

    if return_diagnostics:
        diag = SegmentationDiagnostics(
            dominant_axis=axis,
            signed_rate=signed,
            omega=omega,
            impact_score=impact_score,
            method=method,
            quality={
                "peak_omega_rad_s": peak_omega,
                "impact_snr": float(
                    np.max(impact_score) / (np.median(impact_score) + 1e-9)
                ),
                "quiet_hi": hi,
                "quiet_lo": lo,
                "impact_confidence": float(impact_confidence),
                "fs_hz": float(fs),
            },
            impact_mode=impact_mode,
            impact_confidence=float(impact_confidence),
        )
        return phases, diag
    return phases
