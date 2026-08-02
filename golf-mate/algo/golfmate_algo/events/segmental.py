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

    # --- Impact: strongest broadband transient anywhere in the motion span.
    # The window is deliberately not restricted to high angular rate: an early
    # release ("casting") swing has low wrist rate at impact yet still strikes.
    search_lo = max(0, motion_start - int(0.05 * fs))
    search_hi = min(n - 1, motion_end + int(0.10 * fs))
    seg = impact_score[search_lo : search_hi + 1]
    method = "transient"
    noise_floor = float(np.median(impact_score)) + 1e-9
    if seg.size and float(np.max(seg)) > 4.0 * noise_floor:
        impact_idx = search_lo + int(np.argmax(seg))
    else:
        # Degraded: no clean shock (clipped accel, low ODR). Fall back to rate peak.
        impact_idx = int(np.argmax(omega))
        method = "peak_omega_fallback"

    # --- Top: sign reversal of the signed rate before impact
    peak_idx = int(np.argmax(omega))
    down_sign = np.sign(signed[peak_idx]) if signed[peak_idx] != 0 else 1.0
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

    # --- Address / Finish: hysteresis outward from the motion span
    address_idx = _hysteresis_backward(omega, motion_start, hi, lo)
    address_idx = min(address_idx, max(0, top_idx - 1))
    min_bs = int(min_backswing_s * fs)
    if top_idx - address_idx < min_bs:
        address_idx = max(0, top_idx - min_bs)

    finish_idx = _hysteresis_forward(omega, motion_end, hi, lo)
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
            },
        )
        return phases, diag
    return phases
