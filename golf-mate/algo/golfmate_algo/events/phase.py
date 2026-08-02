"""Swing phase detection from wrist IMU (Address / Top / Impact / Finish)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from golfmate_algo.types import SwingPhases


def _smooth(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return x
    k = np.ones(win, dtype=np.float64) / win
    return np.convolve(x, k, mode="same")


def detect_phases(
    t: ArrayLike,
    gyro: ArrayLike,
    accel: ArrayLike,
    *,
    omega_rest: float = 0.8,
    min_backswing_s: float = 0.35,
    min_downswing_s: float = 0.12,
) -> SwingPhases:
    """Rule-based phase engine for P0.

    Heuristics:
    - Address: end of initial quiet segment
    - Impact: peak of high-pass |a| energy in the motion window (strike spike)
    - Top: omega valley between backswing peak and impact
    - Finish: end of final quieting after post-impact motion
    """
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(accel, dtype=np.float64).reshape(-1, 3)
    n = t.shape[0]
    if n < 10:
        raise ValueError("need at least 10 samples")

    dt = float(np.median(np.diff(t))) if n > 1 else 0.005
    fs = 1.0 / dt
    omega = _smooth(np.linalg.norm(gyro, axis=1), max(3, int(0.02 * fs)))
    acc_mag = np.linalg.norm(accel, axis=1)
    # High-pass-ish: subtract slow envelope to emphasize strike spikes
    acc_env = _smooth(acc_mag, max(5, int(0.08 * fs)))
    spike = np.maximum(acc_mag - acc_env, 0.0)
    spike = _smooth(spike, max(3, int(0.01 * fs)))

    moving = omega > omega_rest
    if not np.any(moving):
        raise ValueError("no motion detected")

    first_move = int(np.argmax(moving))
    last_move = n - 1 - int(np.argmax(moving[::-1]))

    # Address: last quiet index in [0, first_move]
    address = 0
    for i in range(0, first_move + 1):
        if omega[i] <= omega_rest:
            address = i

    # Impact: max spike inside motion, preferring later half but allowing full window
    lo = address + int(0.35 * (last_move - address))
    hi = last_move
    impact = lo + int(np.argmax(spike[lo : hi + 1]))
    # Fallback to peak omega in later portion if spike is flat
    if spike[impact] < 1e-6 or spike[impact] < 0.15 * spike.max():
        lo2 = address + int(0.55 * (last_move - address))
        impact = lo2 + int(np.argmax(omega[lo2 : last_move + 1]))

    # Top: after first backswing omega peak, find valley before impact
    seg = omega[address : impact + 1]
    if seg.size < 5:
        top = address + max(1, (impact - address) // 2)
    else:
        # first peak
        d = np.diff(seg, prepend=seg[0])
        peaks = np.where((d[:-1] > 0) & (d[1:] <= 0))[0]
        if peaks.size == 0:
            top = address + int(0.65 * (impact - address))
        else:
            p0 = int(peaks[0])
            valley_rel = p0 + int(np.argmin(seg[p0:]))
            top = address + valley_rel

        if (top - address) / fs < min_backswing_s:
            top = min(impact - 2, address + int(min_backswing_s * fs))
        if (impact - top) / fs < min_downswing_s:
            top = max(address + 1, impact - int(min_downswing_s * fs))

    # Finish: after impact, find last index where omega drops and stays low,
    # but require some post-impact motion (ignore immediate valley at release).
    min_post = max(3, int(0.08 * fs))
    finish = last_move
    # Search from the end: last quiet sample after impact+min_post
    search_start = min(n - 1, impact + min_post)
    # Prefer last_move if it's quiet-ish; else walk forward from first re-quiet
    for i in range(search_start, n):
        if omega[i] <= omega_rest:
            # ensure we don't stop at a brief dip: look ahead a few samples
            look = omega[i : min(n, i + max(3, int(0.05 * fs)))]
            if look.size and np.mean(look) <= omega_rest * 1.25:
                finish = i
                # continue to extend while still quiet toward end of motion
                for j in range(i, min(n, last_move + 1)):
                    if omega[j] <= omega_rest * 1.5:
                        finish = j
                    else:
                        break
                break
    else:
        finish = max(search_start, last_move)

    top = int(np.clip(top, address + 1, impact - 1))
    impact = int(np.clip(impact, top + 1, finish - 1 if finish > top + 1 else n - 2))
    finish = int(np.clip(max(finish, impact + 1), impact + 1, n - 1))

    phases = SwingPhases(
        address_idx=int(address),
        top_idx=int(top),
        impact_idx=int(impact),
        finish_idx=int(finish),
    )
    phases.validate_order()
    return phases
