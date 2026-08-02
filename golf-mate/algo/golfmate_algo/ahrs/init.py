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
    """Detect quasi-static samples for gyro-bias estimation.

    A sample is considered rest-like when the accelerometer norm is close to
    ``g``, gyro magnitude is low, local gyro variance is low, and local accel
    norm variance is low. Short isolated detections are removed.

    Parameters
    ----------
    gyro, accel:
        ``(N, 3)`` arrays in rad/s and m/s^2.
    fs:
        Sample rate in Hz.
    accel_tol_g:
        Allowed absolute accel-norm deviation as a fraction of ``g``.
    gyro_norm_thresh:
        Maximum gyro norm in rad/s.
    gyro_var_thresh:
        Maximum local summed gyro-axis variance in ``(rad/s)^2``.
    accel_norm_var_thresh:
        Maximum local accel-norm variance in ``(m/s^2)^2``.
    window_s:
        Window used for local variance checks.
    min_duration_s:
        Minimum rest segment duration retained in the output mask.
    """

    gyros = _as_samples(gyro, 3)
    accels = _as_samples(accel, 3)
    if gyros.shape != accels.shape:
        raise ValueError(f"gyro and accel must have matching shape, got {gyros.shape} and {accels.shape}")
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
    if min_len > 1:
        structure = np.ones(min_len, dtype=bool)
        mask = ndimage.binary_opening(mask, structure=structure)
        mask = ndimage.binary_closing(mask, structure=structure)
    return mask.astype(bool)


def _robust_average_accel(accels: ArrayF) -> tuple[ArrayF, NDArray[np.bool_], dict[str, Any]]:
    if accels.shape[0] == 0:
        fallback = np.array([0.0, 0.0, G_NORM], dtype=np.float64)
        return fallback, np.zeros(0, dtype=bool), {
            "median_distance": 0.0,
            "mad_distance": 0.0,
            "accepted_samples": 0,
            "rejected_samples": 0,
        }

    median = np.median(accels, axis=0)
    distances = np.linalg.norm(accels - median, axis=1)
    med_dist = float(np.median(distances))
    mad = float(np.median(np.abs(distances - med_dist)))
    robust_sigma = 1.4826 * mad
    if robust_sigma < 1e-9:
        keep = np.ones(accels.shape[0], dtype=bool)
    else:
        keep = distances <= med_dist + 3.0 * robust_sigma
    if not np.any(keep):
        keep = np.ones(accels.shape[0], dtype=bool)
    avg = np.mean(accels[keep], axis=0)
    metrics = {
        "median_distance": med_dist,
        "mad_distance": mad,
        "accepted_samples": int(np.count_nonzero(keep)),
        "rejected_samples": int(accels.shape[0] - np.count_nonzero(keep)),
    }
    return avg.astype(np.float64), keep, metrics


def _window_scores(gyros: ArrayF, accels: ArrayF, window: int) -> tuple[ArrayF, ArrayF, ArrayF]:
    gyro_norm = np.linalg.norm(gyros, axis=1)
    accel_norm = np.linalg.norm(accels, axis=1)
    gyro_rms = np.sqrt(_moving_mean(gyro_norm * gyro_norm, window))
    accel_deviation = np.abs(_moving_mean(accel_norm, window) - G_NORM) / G_NORM
    gyro_var = np.zeros(gyros.shape[0], dtype=np.float64)
    for axis in range(3):
        gyro_var += _moving_var(gyros[:, axis], window)
    score = gyro_rms + 3.0 * accel_deviation + 2.0 * np.sqrt(gyro_var)
    return score.astype(np.float64), gyro_rms.astype(np.float64), accel_deviation.astype(np.float64)


def estimate_address_orientation(
    gyro: ArrayLike,
    accel: ArrayLike,
    fs: float,
    window_s: float = 0.2,
) -> tuple[ArrayF, slice, dict[str, Any]]:
    """Estimate the initial address quaternion from a quasi-static window.

    The returned quaternion maps body to world and aligns the robustly averaged
    measured specific-force direction with ``UP_WORLD = -G_WORLD / ||G_WORLD||``.
    Heading is unobservable without magnetometer or other external references;
    this function therefore chooses the minimum-tilt rotation from measured
    accel to world up. That convention sets yaw to zero relative to the sensor's
    address frame while preserving the observable roll/pitch.
    """

    gyros = _as_samples(gyro, 3)
    accels = _as_samples(accel, 3)
    if gyros.shape != accels.shape:
        raise ValueError(f"gyro and accel must have matching shape, got {gyros.shape} and {accels.shape}")
    n = gyros.shape[0]
    if n == 0:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64), slice(0, 0), {
            "quality": "empty_input",
            "accepted_samples": 0,
            "rest_fraction": 0.0,
        }

    fs_hz = max(float(fs), 1e-6)
    window = min(max(int(round(window_s * fs_hz)), 1), n)
    rest_mask = rest_detection(
        gyros,
        accels,
        fs_hz,
        window_s=min(window_s, 0.15),
        min_duration_s=min(window_s, 0.05),
    )

    csum_rest = np.concatenate([[0], np.cumsum(rest_mask.astype(np.int64))])
    rest_counts = csum_rest[window:] - csum_rest[:-window]
    if rest_counts.size == 0:
        start = 0
    elif np.max(rest_counts) > 0:
        candidates = np.flatnonzero(rest_counts == np.max(rest_counts))
        score, _, _ = _window_scores(gyros, accels, window)
        centers = np.clip(candidates + window // 2, 0, n - 1)
        start = int(candidates[int(np.argmin(score[centers]))])
    else:
        score, _, _ = _window_scores(gyros, accels, window)
        valid_centers = np.arange(window // 2, n - (window - 1) // 2)
        if valid_centers.size == 0:
            start = 0
        else:
            center = int(valid_centers[int(np.argmin(score[valid_centers]))])
            start = int(np.clip(center - window // 2, 0, n - window))

    stop = min(start + window, n)
    window_slice = slice(start, stop)
    accel_window = accels[window_slice]
    gyro_window = gyros[window_slice]
    accel_avg, keep, robust_metrics = _robust_average_accel(accel_window)
    accel_norm = float(np.linalg.norm(accel_avg))
    if accel_norm < 1e-9:
        accel_avg = np.array([0.0, 0.0, G_NORM], dtype=np.float64)
        accel_norm = G_NORM
    accel_hat = accel_avg / accel_norm
    q0 = so3.quat_from_two_vectors(accel_hat, UP_WORLD)
    q0 = so3.normalize_quat(q0)
    if q0[0] < 0.0:
        q0 = -q0

    kept_accel_norm = np.linalg.norm(accel_window[keep], axis=1) if np.any(keep) else np.array([], dtype=np.float64)
    gyro_norm = np.linalg.norm(gyro_window, axis=1)
    accel_norm_all = np.linalg.norm(accel_window, axis=1)
    rest_fraction = float(np.mean(rest_mask[window_slice])) if stop > start else 0.0
    gyro_rms = float(np.sqrt(np.mean(gyro_norm * gyro_norm))) if gyro_norm.size else 0.0
    accel_norm_mean = float(np.mean(kept_accel_norm)) if kept_accel_norm.size else 0.0
    accel_norm_std = float(np.std(kept_accel_norm)) if kept_accel_norm.size else 0.0
    norm_error_g = abs(accel_norm_mean - G_NORM) / G_NORM if accel_norm_mean > 0.0 else float("inf")
    quality_score = float(gyro_rms + 3.0 * norm_error_g + accel_norm_std / G_NORM)
    if rest_fraction >= 0.5 and norm_error_g < 0.08 and gyro_rms < 0.35:
        quality = "good"
    elif norm_error_g < 0.15 and gyro_rms < 0.75:
        quality = "usable"
    else:
        quality = "poor"

    metrics: dict[str, Any] = {
        "quality": quality,
        "quality_score": quality_score,
        "window_start": int(start),
        "window_stop": int(stop),
        "window_samples": int(stop - start),
        "window_s": float((stop - start) / fs_hz),
        "rest_fraction": rest_fraction,
        "gyro_norm_rms": gyro_rms,
        "gyro_norm_mean": float(np.mean(gyro_norm)) if gyro_norm.size else 0.0,
        "accel_norm_mean": accel_norm_mean,
        "accel_norm_std": accel_norm_std,
        "accel_norm_error_g": float(norm_error_g),
        "accel_norm_mean_raw": float(np.mean(accel_norm_all)) if accel_norm_all.size else 0.0,
        "robust_accel": accel_avg,
        "heading_convention": "minimum-tilt rotation aligning measured specific force to world up; yaw set to 0",
        "rest_mask": rest_mask,
    }
    metrics.update(robust_metrics)
    return q0.astype(np.float64), window_slice, metrics
