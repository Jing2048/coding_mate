"""Initialization utilities for 6-axis golf-swing orientation filters."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import ndimage

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]
G_NORM = float(np.linalg.norm(so3.G_WORLD))
UP_WORLD = -so3.G_WORLD / G_NORM


def _as_samples(x: ArrayLike, width: int) -> ArrayF:
    arr = np.asarray(x, dtype=np.float64).reshape(-1, width)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)


def _moving_mean(x: ArrayLike, window: int) -> ArrayF:
    arr = np.asarray(x, dtype=np.float64)
    if arr.size == 0:
        return arr.astype(np.float64)
    window = max(int(window), 1)
    if window == 1:
        return arr.astype(np.float64)
    return ndimage.uniform_filter1d(arr.astype(np.float64), size=window, mode="nearest")


def _moving_var(x: ArrayLike, window: int) -> ArrayF:
    arr = np.asarray(x, dtype=np.float64)
    mean = _moving_mean(arr, window)
    mean_sq = _moving_mean(arr * arr, window)
    return np.maximum(mean_sq - mean * mean, 0.0).astype(np.float64)


def rest_detection(
    gyro: ArrayLike,
    accel: ArrayLike,
    fs: float,
    *,
    accel_tol_g: float = 0.08,
    gyro_norm_thresh: float = 0.25,
    gyro_var_thresh: float = 0.03,
    accel_norm_var_thresh: float = 0.35,
    window_s: float = 0.10,
    min_duration_s: float = 0.05,
) -> NDArray[np.bool_]:
    """Detect quasi-static samples usable for gyro-bias estimation.

    A sample is rest-like when the accelerometer norm is close to ``g``, gyro
    magnitude is low, and both local variances are low. Isolated detections are
    removed by a morphological opening so a single quiet sample inside the swing
    cannot corrupt the bias estimate.
    """
    gyros = _as_samples(gyro, 3)
    accels = _as_samples(accel, 3)
    if gyros.shape != accels.shape:
        raise ValueError("gyro and accel must have matching shape")
    n = gyros.shape[0]
    if n == 0:
        return np.zeros(0, dtype=bool)

    fs_hz = max(float(fs), 1e-6)
    window = max(int(round(window_s * fs_hz)), 1)
    accel_norm = np.linalg.norm(accels, axis=1)
    gyro_norm = np.linalg.norm(gyros, axis=1)
    gyro_var = np.zeros(n, dtype=np.float64)
    for axis in range(3):
        gyro_var += _moving_var(gyros[:, axis], window)
    accel_norm_var = _moving_var(accel_norm, window)

    mask = (
        (np.abs(accel_norm - G_NORM) <= accel_tol_g * G_NORM)
        & (gyro_norm <= gyro_norm_thresh)
        & (gyro_var <= gyro_var_thresh)
        & (accel_norm_var <= accel_norm_var_thresh)
    )

    min_len = max(int(round(min_duration_s * fs_hz)), 1)
    if min_len > 1 and mask.any():
        structure = np.ones(min_len, dtype=bool)
        mask = ndimage.binary_opening(mask, structure=structure)
    return mask.astype(bool)


def _robust_average_accel(accels: ArrayF) -> tuple[ArrayF, NDArray[np.bool_], dict[str, Any]]:
    """Median + MAD outlier rejection, then mean of the inliers."""
    if accels.shape[0] == 0:
        fallback = np.array([0.0, 0.0, G_NORM], dtype=np.float64)
        return fallback, np.zeros(0, dtype=bool), {"accepted_samples": 0, "rejected_samples": 0}

    median = np.median(accels, axis=0)
    distances = np.linalg.norm(accels - median, axis=1)
    med_dist = float(np.median(distances))
    mad = float(np.median(np.abs(distances - med_dist)))
    robust_sigma = 1.4826 * mad
    keep = (
        np.ones(accels.shape[0], dtype=bool)
        if robust_sigma < 1e-9
        else distances <= med_dist + 3.0 * robust_sigma
    )
    if not np.any(keep):
        keep = np.ones(accels.shape[0], dtype=bool)
    avg = np.mean(accels[keep], axis=0)
    return (
        avg.astype(np.float64),
        keep,
        {
            "accepted_samples": int(np.count_nonzero(keep)),
            "rejected_samples": int(accels.shape[0] - np.count_nonzero(keep)),
            "mad_distance": mad,
        },
    )


def estimate_address_orientation(
    gyro: ArrayLike,
    accel: ArrayLike,
    fs: float,
    window_s: float = 0.2,
) -> tuple[ArrayF, slice, dict[str, Any]]:
    """Estimate the address quaternion from the quietest quasi-static window.

    Heading is unobservable from a 6-axis IMU, so the convention here is the
    minimum-tilt rotation taking the robustly averaged specific force to world
    up, which leaves yaw at zero in the address frame. Downstream metrics are
    therefore reported relative to address, not to an absolute heading.
    """
    gyros = _as_samples(gyro, 3)
    accels = _as_samples(accel, 3)
    n = gyros.shape[0]
    if n == 0:
        return (
            np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
            slice(0, 0),
            {"quality": "empty_input"},
        )

    fs_hz = max(float(fs), 1e-6)
    window = min(max(int(round(window_s * fs_hz)), 1), n)

    gyro_norm = np.linalg.norm(gyros, axis=1)
    accel_norm = np.linalg.norm(accels, axis=1)
    gyro_rms = np.sqrt(_moving_mean(gyro_norm**2, window))
    accel_dev = np.abs(_moving_mean(accel_norm, window) - G_NORM) / G_NORM
    # Prefer the earliest acceptable quiet window. Over a long session there are
    # many quiet windows in different poses; the address of the first swing is
    # the one the filter must be initialised from, so a small monotone penalty
    # breaks ties in favour of earlier windows.
    recency_penalty = 0.02 * np.arange(n, dtype=np.float64) / max(n - 1, 1)
    score = gyro_rms + 3.0 * accel_dev + recency_penalty

    valid = np.arange(window // 2, max(window // 2 + 1, n - (window - 1) // 2))
    center = int(valid[int(np.argmin(score[valid]))]) if valid.size else 0
    start = int(np.clip(center - window // 2, 0, max(0, n - window)))
    stop = min(start + window, n)
    window_slice = slice(start, stop)

    accel_avg, keep, robust_metrics = _robust_average_accel(accels[window_slice])
    norm = float(np.linalg.norm(accel_avg))
    if norm < 1e-9:
        accel_avg = np.array([0.0, 0.0, G_NORM], dtype=np.float64)
        norm = G_NORM
    q0 = so3.normalize_quat(so3.quat_from_two_vectors(accel_avg / norm, UP_WORLD))
    if q0[0] < 0.0:
        q0 = -q0

    win_gyro_rms = float(np.sqrt(np.mean(gyro_norm[window_slice] ** 2))) if stop > start else 0.0
    norm_err = abs(norm - G_NORM) / G_NORM
    if norm_err < 0.08 and win_gyro_rms < 0.35:
        quality = "good"
    elif norm_err < 0.15 and win_gyro_rms < 0.75:
        quality = "usable"
    else:
        quality = "poor"

    metrics: dict[str, Any] = {
        "quality": quality,
        "window_start": int(start),
        "window_stop": int(stop),
        "gyro_norm_rms": win_gyro_rms,
        "accel_norm_error_g": float(norm_err),
        "heading_convention": "min-tilt to world up; yaw = 0 in address frame",
    }
    metrics.update(robust_metrics)
    return q0.astype(np.float64), window_slice, metrics


def estimate_gyro_bias(
    gyro: ArrayLike, accel: ArrayLike, fs: float, **kwargs: Any
) -> tuple[ArrayF, float]:
    """Mean gyro over detected rest samples. Returns (bias, rest_fraction)."""
    gyros = _as_samples(gyro, 3)
    mask = rest_detection(gyros, accel, fs, **kwargs)
    if not mask.any():
        return np.zeros(3, dtype=np.float64), 0.0
    return gyros[mask].mean(axis=0), float(np.mean(mask))
