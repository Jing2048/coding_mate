"""Physically-motivated IMU error model for adversarial validation.

Applies, in measurement order:
    ideal → soft-tissue/mount compliance → misalignment & non-orthogonality
          → scale factor → bias (constant + random walk) → g-sensitivity
          → white noise → saturation/clipping → quantization
          → sample jitter / dropouts

References for the error terms: Allan-variance IMU noise modelling
(ARW/VRW, bias instability) and standard strapdown error budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]

# Representative consumer/high-ODR MEMS parts (BMI270 / ICM-42688-P class).
DEG = np.pi / 180.0


@dataclass
class ImuErrorParams:
    """All-zero defaults mean an ideal sensor (useful for regression baselines)."""

    # White noise densities
    gyro_arw_deg_s_sqrt_hz: float = 0.0  # angle random walk
    accel_vrw_m_s2_sqrt_hz: float = 0.0  # velocity random walk

    # Bias: constant turn-on + random walk
    gyro_bias_const_deg_s: float = 0.0
    accel_bias_const_m_s2: float = 0.0
    gyro_bias_rw_deg_s_sqrt_s: float = 0.0
    accel_bias_rw_m_s2_sqrt_s: float = 0.0

    # Deterministic errors
    gyro_scale_err_ppm: float = 0.0  # per-axis scale factor error
    accel_scale_err_ppm: float = 0.0
    nonorthogonality_deg: float = 0.0  # axis non-orthogonality magnitude
    misalignment_deg: float = 0.0  # sensor-to-mount misalignment

    # Cross-coupling
    gyro_g_sensitivity_deg_s_per_g: float = 0.0

    # Range limits (saturation)
    gyro_range_deg_s: float = np.inf
    accel_range_g: float = np.inf

    # Digitization
    gyro_lsb_deg_s: float = 0.0
    accel_lsb_m_s2: float = 0.0

    # Mount compliance (soft tissue / glove card wobble): 2nd-order resonance
    mount_resonance_hz: float = 0.0  # 0 disables
    mount_damping: float = 0.7
    mount_gain: float = 0.0  # 0 disables; fraction of signal passed through mode

    # Timing
    jitter_std_s: float = 0.0
    dropout_prob: float = 0.0
    dropout_max_len: int = 3

    seed: int | None = None

    @staticmethod
    def ideal() -> "ImuErrorParams":
        return ImuErrorParams()

    @staticmethod
    def consumer_grade(seed: int | None = 0) -> "ImuErrorParams":
        """BMI270 / ICM-42688-P class wrist wearable."""
        return ImuErrorParams(
            gyro_arw_deg_s_sqrt_hz=0.007,
            accel_vrw_m_s2_sqrt_hz=0.0015,
            gyro_bias_const_deg_s=1.0,
            accel_bias_const_m_s2=0.05,
            gyro_bias_rw_deg_s_sqrt_s=0.002,
            accel_bias_rw_m_s2_sqrt_s=0.0008,
            gyro_scale_err_ppm=5000.0,
            accel_scale_err_ppm=3000.0,
            nonorthogonality_deg=0.2,
            misalignment_deg=0.5,
            gyro_g_sensitivity_deg_s_per_g=0.1,
            gyro_range_deg_s=2000.0,
            accel_range_g=16.0,
            gyro_lsb_deg_s=0.061,
            accel_lsb_m_s2=0.0048,
            mount_resonance_hz=18.0,
            mount_damping=0.35,
            mount_gain=0.05,
            jitter_std_s=0.0,
            dropout_prob=0.0,
            seed=seed,
        )

    @staticmethod
    def harsh(seed: int | None = 0) -> "ImuErrorParams":
        """Loose glove mount, cheap part, saturating gyro, lossy link."""
        p = ImuErrorParams.consumer_grade(seed=seed)
        p.gyro_arw_deg_s_sqrt_hz = 0.02
        p.accel_vrw_m_s2_sqrt_hz = 0.004
        p.gyro_bias_const_deg_s = 3.0
        p.accel_bias_const_m_s2 = 0.15
        p.gyro_range_deg_s = 1000.0  # will clip a real downswing
        p.accel_range_g = 8.0
        p.misalignment_deg = 2.0
        p.nonorthogonality_deg = 0.6
        p.mount_gain = 0.18
        p.mount_damping = 0.2
        p.jitter_std_s = 0.0005
        p.dropout_prob = 0.002
        return p


@dataclass
class ImuErrorReport:
    gyro_saturated_frac: float
    accel_saturated_frac: float
    dropout_frac: float
    applied: dict[str, float] = field(default_factory=dict)


def _skew_misalignment(rng: np.random.Generator, angle_deg: float) -> ArrayF:
    """Small-angle rotation matrix with random axis (sensor mount misalignment)."""
    if angle_deg <= 0.0:
        return np.eye(3, dtype=np.float64)
    axis = rng.normal(size=3)
    axis /= np.linalg.norm(axis) + 1e-12
    a = angle_deg * DEG
    K = np.array(
        [
            [0.0, -axis[2], axis[1]],
            [axis[2], 0.0, -axis[0]],
            [-axis[1], axis[0], 0.0],
        ],
        dtype=np.float64,
    )
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * (K @ K)


def _nonorthogonal_matrix(rng: np.random.Generator, angle_deg: float) -> ArrayF:
    """Upper-triangular small-angle non-orthogonality (axis skew)."""
    if angle_deg <= 0.0:
        return np.eye(3, dtype=np.float64)
    a = angle_deg * DEG
    M = np.eye(3, dtype=np.float64)
    M[0, 1] = rng.normal(scale=a)
    M[0, 2] = rng.normal(scale=a)
    M[1, 2] = rng.normal(scale=a)
    return M


def _second_order_mount(x: ArrayF, fs: float, f0: float, zeta: float, gain: float) -> ArrayF:
    """Add a lightly damped resonance component (soft tissue / loose mount).

    Implemented as a discrete 2nd-order resonator driven by the signal derivative,
    scaled by ``gain``; returns x + gain * mode_response.
    """
    if gain <= 0.0 or f0 <= 0.0:
        return x
    dt = 1.0 / fs
    w0 = 2 * np.pi * f0
    y = np.zeros_like(x)
    v = np.zeros(x.shape[1], dtype=np.float64)
    p = np.zeros(x.shape[1], dtype=np.float64)
    drive = np.vstack([np.zeros((1, x.shape[1])), np.diff(x, axis=0)]) / dt
    for i in range(x.shape[0]):
        a = drive[i] - 2 * zeta * w0 * v - (w0**2) * p
        v = v + a * dt
        p = p + v * dt
        y[i] = p
    # Normalize mode magnitude so gain is an approximate amplitude fraction
    scale = np.max(np.abs(x)) / (np.max(np.abs(y)) + 1e-9) if np.max(np.abs(y)) > 0 else 0.0
    return x + gain * scale * y


def apply_imu_errors(
    t: ArrayLike,
    gyro_ideal: ArrayLike,
    accel_ideal: ArrayLike,
    params: ImuErrorParams,
) -> tuple[ArrayF, ArrayF, ArrayF, ImuErrorReport]:
    """Corrupt ideal IMU signals. Returns (t_out, gyro, accel, report)."""
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    g_in = np.asarray(gyro_ideal, dtype=np.float64).reshape(-1, 3).copy()
    a_in = np.asarray(accel_ideal, dtype=np.float64).reshape(-1, 3).copy()
    n = t.shape[0]
    if n < 2:
        raise ValueError("need >= 2 samples")
    fs = 1.0 / float(np.median(np.diff(t)))
    rng = np.random.default_rng(params.seed)

    # 1. Mount compliance (acts on both channels; wrist card wobble)
    g_s = _second_order_mount(
        g_in, fs, params.mount_resonance_hz, params.mount_damping, params.mount_gain
    )
    a_s = _second_order_mount(
        a_in, fs, params.mount_resonance_hz, params.mount_damping, params.mount_gain
    )

    # 2. Misalignment + non-orthogonality
    R_mis = _skew_misalignment(rng, params.misalignment_deg)
    M_g = _nonorthogonal_matrix(rng, params.nonorthogonality_deg)
    M_a = _nonorthogonal_matrix(rng, params.nonorthogonality_deg)
    g_s = (M_g @ R_mis @ g_s.T).T
    a_s = (M_a @ R_mis @ a_s.T).T

    # 3. Scale factor error (per axis)
    sf_g = 1.0 + rng.normal(scale=params.gyro_scale_err_ppm * 1e-6, size=3)
    sf_a = 1.0 + rng.normal(scale=params.accel_scale_err_ppm * 1e-6, size=3)
    g_s *= sf_g
    a_s *= sf_a

    # 4. Bias: constant turn-on + random walk
    b_g0 = rng.normal(scale=params.gyro_bias_const_deg_s * DEG, size=3)
    b_a0 = rng.normal(scale=params.accel_bias_const_m_s2, size=3)
    dt = 1.0 / fs
    rw_g = np.cumsum(
        rng.normal(scale=params.gyro_bias_rw_deg_s_sqrt_s * DEG * np.sqrt(dt), size=(n, 3)),
        axis=0,
    )
    rw_a = np.cumsum(
        rng.normal(scale=params.accel_bias_rw_m_s2_sqrt_s * np.sqrt(dt), size=(n, 3)),
        axis=0,
    )
    g_s = g_s + b_g0 + rw_g
    a_s = a_s + b_a0 + rw_a

    # 5. Gyro g-sensitivity (acceleration leaks into rate)
    if params.gyro_g_sensitivity_deg_s_per_g > 0:
        g_s = g_s + (params.gyro_g_sensitivity_deg_s_per_g * DEG) * (a_s / 9.80665)

    # 6. White noise (ARW/VRW densities → per-sample sigma)
    if params.gyro_arw_deg_s_sqrt_hz > 0:
        sigma = params.gyro_arw_deg_s_sqrt_hz * DEG * np.sqrt(fs)
        g_s = g_s + rng.normal(scale=sigma, size=(n, 3))
    if params.accel_vrw_m_s2_sqrt_hz > 0:
        sigma = params.accel_vrw_m_s2_sqrt_hz * np.sqrt(fs)
        a_s = a_s + rng.normal(scale=sigma, size=(n, 3))

    # 7. Saturation
    g_lim = params.gyro_range_deg_s * DEG
    a_lim = params.accel_range_g * 9.80665
    g_sat = float(np.mean(np.abs(g_s) > g_lim)) if np.isfinite(g_lim) else 0.0
    a_sat = float(np.mean(np.abs(a_s) > a_lim)) if np.isfinite(a_lim) else 0.0
    g_s = np.clip(g_s, -g_lim, g_lim)
    a_s = np.clip(a_s, -a_lim, a_lim)

    # 8. Quantization
    if params.gyro_lsb_deg_s > 0:
        q = params.gyro_lsb_deg_s * DEG
        g_s = np.round(g_s / q) * q
    if params.accel_lsb_m_s2 > 0:
        q = params.accel_lsb_m_s2
        a_s = np.round(a_s / q) * q

    # 9. Timing jitter
    t_out = t.copy()
    if params.jitter_std_s > 0:
        t_out = t + rng.normal(scale=params.jitter_std_s, size=n)
        t_out = np.maximum.accumulate(t_out)

    # 10. Dropouts: hold last sample (typical BLE behaviour)
    drop_frac = 0.0
    if params.dropout_prob > 0:
        mask = rng.random(n) < params.dropout_prob
        idx = np.where(mask)[0]
        dropped = 0
        for i in idx:
            ln = int(rng.integers(1, params.dropout_max_len + 1))
            hi = min(n, i + ln)
            if i > 0:
                g_s[i:hi] = g_s[i - 1]
                a_s[i:hi] = a_s[i - 1]
                dropped += hi - i
        drop_frac = dropped / n

    report = ImuErrorReport(
        gyro_saturated_frac=g_sat,
        accel_saturated_frac=a_sat,
        dropout_frac=drop_frac,
        applied={
            "fs_hz": fs,
            "gyro_bias_const_norm_rad_s": float(np.linalg.norm(b_g0)),
            "accel_bias_const_norm_m_s2": float(np.linalg.norm(b_a0)),
        },
    )
    return t_out, g_s, a_s, report
