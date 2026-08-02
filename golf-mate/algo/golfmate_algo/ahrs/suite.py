"""Orientation-estimation filters for golf swing IMU benchmarking.

All estimators in this module use the package convention:

* quaternions are scalar-first ``[w, x, y, z]`` and map body vectors to world
* gyro is body angular rate in rad/s
* accel is measured specific force in m/s^2
* world gravity is ``G_WORLD = [0, 0, -9.80665]``
* static accel satisfies ``a_meas ~= -R(q).T @ G_WORLD``

Yaw is unobservable for these 6-axis IMU filters. Accelerometer updates only
constrain tilt, so each filter's yaw behavior is determined by gyro integration
and any estimated gyro bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]

G_NORM = float(np.linalg.norm(so3.G_WORLD))
UP_WORLD = -so3.G_WORLD / G_NORM
IDENTITY_QUAT = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)


class OrientationEstimator(Protocol):
    """Common interface for orientation filters used in benchmarking."""

    name: str

    def reset(self, q0: ArrayLike | None = None) -> None:
        """Reset the estimator state."""
        ...

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        """Process one sample and return the current quaternion."""
        ...

    def run(
        self,
        gyro_seq: ArrayLike,
        accel_seq: ArrayLike,
        dt: float | ArrayLike,
        q0: ArrayLike | None = None,
    ) -> tuple[ArrayF, dict[str, Any]]:
        """Process a sequence and return quaternions plus diagnostics."""
        ...


@dataclass(frozen=True)
class FilterTuningSummary:
    """Human-readable tuning guidance for a filter."""

    filter_name: str
    parameters: str
    strengths: str
    weaknesses: str


TUNING_TABLE: tuple[FilterTuningSummary, ...] = (
    FilterTuningSummary(
        "GyroOnly",
        "No correction parameters.",
        "Best short-window dynamic fidelity when gyro bias is known or negligible.",
        "Roll/pitch/yaw drift; no recovery from bad initial tilt.",
    ),
    FilterTuningSummary(
        "Complementary",
        "gain: first-order tilt correction rate in 1/s.",
        "Simple, deterministic baseline; good during quiet address and finish.",
        "Accelerometer correction is fixed, so impact/centripetal acceleration can corrupt tilt.",
    ),
    FilterTuningSummary(
        "MahonyAHRS",
        "kp: proportional tilt gain, ki: integral gyro-bias gain.",
        "Bias-aware SO(3) complementary filter; robust and inexpensive.",
        "Integral bias can be pulled by sustained non-gravity acceleration unless tuned conservatively.",
    ),
    FilterTuningSummary(
        "MadgwickAHRS",
        "beta: normalized gradient-descent correction gain.",
        "Strong open-source-comparable 6-axis baseline; handles large initial tilt error.",
        "Single beta trades convergence against high-dynamic accel sensitivity.",
    ),
    FilterTuningSummary(
        "EKFOrientation",
        "gyro_noise, bias_rw, accel_dir_noise, accel_sigma, max_noise_scale.",
        "Principled bias and covariance tracking; accel trust is reduced smoothly in high dynamics.",
        "More tuning and compute; yaw and yaw bias remain weakly observable without magnetometer.",
    ),
    FilterTuningSummary(
        "GatedAdaptive",
        "tilt_gain, sigma_a, sigma_w, bias_tau_s, rest thresholds.",
        "Golf-specific smooth accel trust and rest-only gyro bias learning.",
        "Needs representative sigma tuning across clubs/sensors; no full covariance model.",
    ),
)


def tuning_table_as_dicts() -> list[dict[str, str]]:
    """Return the filter tuning table as serializable dictionaries."""

    return [summary.__dict__.copy() for summary in TUNING_TABLE]


def _as_vec3(x: ArrayLike) -> ArrayF:
    v = np.asarray(x, dtype=np.float64).reshape(3)
    return np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)


def _safe_dt(dt: float) -> float:
    out = float(np.nan_to_num(dt, nan=0.0, posinf=0.0, neginf=0.0))
    return max(out, 0.0)


def _sanitize_quat(q: ArrayLike, ref: ArrayLike | None = None) -> ArrayF:
    q_arr = np.asarray(q, dtype=np.float64).reshape(4)
    q_arr = np.nan_to_num(q_arr, nan=0.0, posinf=0.0, neginf=0.0)
    q_arr = so3.normalize_quat(q_arr)
    if ref is not None:
        q_arr = so3.ensure_quat_hemisphere(q_arr, ref)
    return q_arr


def _unit_or_none(v: ArrayLike, eps: float = 1e-9) -> ArrayF | None:
    arr = _as_vec3(v)
    n = float(np.linalg.norm(arr))
    if not np.isfinite(n) or n < eps:
        return None
    return arr / n


def _prepare_sequences(
    gyro_seq: ArrayLike, accel_seq: ArrayLike, dt: float | ArrayLike
) -> tuple[ArrayF, ArrayF, ArrayF]:
    gyros = np.asarray(gyro_seq, dtype=np.float64).reshape(-1, 3)
    accels = np.asarray(accel_seq, dtype=np.float64).reshape(-1, 3)
    if gyros.shape != accels.shape:
        raise ValueError(
            f"gyro_seq and accel_seq must have matching shape, got {gyros.shape} and {accels.shape}"
        )
    gyros = np.nan_to_num(gyros, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)
    accels = np.nan_to_num(accels, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)
    n = gyros.shape[0]
    dt_arr = np.asarray(dt, dtype=np.float64)
    if dt_arr.ndim == 0:
        dts = np.full(n, _safe_dt(float(dt_arr)), dtype=np.float64)
    else:
        dts = np.nan_to_num(dt_arr.reshape(-1), nan=0.0, posinf=0.0, neginf=0.0)
        if dts.shape[0] != n:
            raise ValueError(f"dt sequence length must be {n}, got {dts.shape[0]}")
        dts = np.maximum(dts.astype(np.float64), 0.0)
    return gyros, accels, dts


def _skew(v: ArrayLike) -> ArrayF:
    x, y, z = _as_vec3(v)
    return np.array(
        [[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]],
        dtype=np.float64,
    )


def _predicted_specific_force(q: ArrayLike) -> ArrayF:
    """Return static accelerometer prediction ``-R(q).T @ G_WORLD``."""

    R = so3.quat_to_rotmat(q)
    return -R.T @ so3.G_WORLD


def _predicted_up_body(q: ArrayLike) -> ArrayF:
    return _predicted_specific_force(q) / G_NORM


def quat_slerp(q0: ArrayLike, q1: ArrayLike, t: float) -> ArrayF:
    """Spherical linear interpolation with hemisphere handling."""

    t = float(np.clip(t, 0.0, 1.0))
    qa = _sanitize_quat(q0)
    qb = _sanitize_quat(q1)
    dot = float(np.dot(qa, qb))
    if dot < 0.0:
        qb = -qb
        dot = -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        return so3.normalize_quat(qa + t * (qb - qa))
    theta = float(np.arccos(dot))
    denom = float(np.sin(theta))
    if abs(denom) < 1e-12:
        return qa.copy()
    a = np.sin((1.0 - t) * theta) / denom
    b = np.sin(t * theta) / denom
    return so3.normalize_quat(a * qa + b * qb)


def _small_angle_quat(delta: ArrayLike) -> ArrayF:
    delta = _as_vec3(delta)
    angle = float(np.linalg.norm(delta))
    if angle < 1e-12:
        return IDENTITY_QUAT.copy()
    return so3.quat_from_axis_angle(delta / angle, angle)


def _apply_world_tilt_correction(q: ArrayLike, accel: ArrayLike, alpha: float) -> ArrayF:
    """Apply a yaw-free accel tilt correction by left-multiplying in world frame."""

    alpha = float(np.clip(alpha, 0.0, 1.0))
    q_in = _sanitize_quat(q)
    if alpha <= 0.0:
        return q_in
    a_hat = _unit_or_none(accel)
    if a_hat is None:
        return q_in

    R = so3.quat_to_rotmat(q_in)
    measured_up_world = R @ a_hat
    q_err = so3.quat_from_two_vectors(measured_up_world, UP_WORLD)
    q_corr = quat_slerp(IDENTITY_QUAT, q_err, alpha)
    return so3.normalize_quat(so3.quat_multiply(q_corr, q_in))


class _EstimatorBase:
    name = "base"

    def __init__(self) -> None:
        self.q = IDENTITY_QUAT.copy()

    def reset(self, q0: ArrayLike | None = None) -> None:
        self.q = _sanitize_quat(q0) if q0 is not None else IDENTITY_QUAT.copy()
        self._reset_history()

    def _reset_history(self) -> None:
        pass

    def diagnostics(self) -> dict[str, Any]:
        return {}

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        raise NotImplementedError

    def run(
        self,
        gyro_seq: ArrayLike,
        accel_seq: ArrayLike,
        dt: float | ArrayLike,
        q0: ArrayLike | None = None,
    ) -> tuple[ArrayF, dict[str, Any]]:
        gyros, accels, dts = _prepare_sequences(gyro_seq, accel_seq, dt)
        self.reset(q0)
        quats = np.zeros((gyros.shape[0], 4), dtype=np.float64)
        prev = self.q.copy()
        for i, (gyro_i, accel_i, dt_i) in enumerate(zip(gyros, accels, dts)):
            quats[i] = self.update(gyro_i, accel_i, float(dt_i))
            quats[i] = _sanitize_quat(quats[i], prev)
            self.q = quats[i].copy()
            prev = quats[i].copy()
        return quats, self.diagnostics()


class GyroOnly(_EstimatorBase):
    """Pure strapdown gyro integration.

    This is a drift reference and an upper baseline for very short swing
    windows, not a complete tilt estimator.
    """

    name = "gyro_only"

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        del accel
        q_prev = self.q.copy()
        self.q = so3.integrate_gyro_rk4(self.q, _as_vec3(gyro), _safe_dt(dt))
        self.q = _sanitize_quat(self.q, q_prev)
        return self.q.copy()


class Complementary(_EstimatorBase):
    """Classic fixed-gain tilt complementary filter."""

    name = "complementary"

    def __init__(self, gain: float = 2.0) -> None:
        super().__init__()
        self.gain = float(gain)
        self.gain_history: list[float] = []
        self.alpha_history: list[float] = []
        self.accel_norm_history: list[float] = []

    def _reset_history(self) -> None:
        self.gain_history = []
        self.alpha_history = []
        self.accel_norm_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v = _as_vec3(gyro)
        accel_v = _as_vec3(accel)
        dt_s = _safe_dt(dt)
        q_prev = self.q.copy()
        q_pred = so3.integrate_gyro_rk4(self.q, gyro_v, dt_s)
        alpha = 1.0 - float(np.exp(-max(self.gain, 0.0) * dt_s))
        q_new = _apply_world_tilt_correction(q_pred, accel_v, alpha)
        self.q = _sanitize_quat(q_new, q_prev)
        self.gain_history.append(max(self.gain, 0.0))
        self.alpha_history.append(alpha)
        self.accel_norm_history.append(float(np.linalg.norm(accel_v)))
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "gain": self.gain,
            "gain_history": np.asarray(self.gain_history, dtype=np.float64),
            "alpha_history": np.asarray(self.alpha_history, dtype=np.float64),
            "accel_norm": np.asarray(self.accel_norm_history, dtype=np.float64),
        }


class MahonyAHRS(_EstimatorBase):
    """Passive Mahony complementary filter on SO(3) with gyro-bias estimation."""

    name = "mahony"

    def __init__(self, kp: float = 2.0, ki: float = 0.05, initial_bias: ArrayLike | None = None) -> None:
        super().__init__()
        self.kp = float(kp)
        self.ki = float(ki)
        self.initial_bias = _as_vec3(initial_bias) if initial_bias is not None else np.zeros(3)
        self.bias = self.initial_bias.copy()
        self.bias_history: list[ArrayF] = []
        self.error_history: list[ArrayF] = []
        self.accel_norm_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = self.initial_bias.copy()

    def _reset_history(self) -> None:
        self.bias_history = []
        self.error_history = []
        self.accel_norm_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v = _as_vec3(gyro)
        accel_v = _as_vec3(accel)
        dt_s = _safe_dt(dt)
        q_prev = self.q.copy()
        error = np.zeros(3, dtype=np.float64)

        a_hat = _unit_or_none(accel_v)
        if a_hat is not None:
            up_pred = _predicted_up_body(self.q)
            # Sign convention: measured x predicted gives a body-frame correction
            # that rotates the estimated "up" direction toward accelerometer up.
            error = np.cross(a_hat, up_pred)
            if self.ki > 0.0 and dt_s > 0.0:
                self.bias += -self.ki * error * dt_s

        omega = gyro_v - self.bias + self.kp * error
        self.q = so3.integrate_gyro_rk4(self.q, omega, dt_s)
        self.q = _sanitize_quat(self.q, q_prev)
        self.bias_history.append(self.bias.copy())
        self.error_history.append(error.copy())
        self.accel_norm_history.append(float(np.linalg.norm(accel_v)))
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "kp": self.kp,
            "ki": self.ki,
            "bias": np.asarray(self.bias_history, dtype=np.float64),
            "tilt_error": np.asarray(self.error_history, dtype=np.float64),
            "accel_norm": np.asarray(self.accel_norm_history, dtype=np.float64),
        }


class MadgwickAHRS(_EstimatorBase):
    """Madgwick 6-axis IMU gradient-descent filter.

    The objective minimizes the difference between measured accel direction and
    ``R(q).T @ [0, 0, 1]``. No magnetometer is used, so yaw remains gyro-only.
    """

    name = "madgwick"

    def __init__(self, beta: float = 0.1) -> None:
        super().__init__()
        self.beta = float(beta)
        self.gradient_norm_history: list[float] = []
        self.accel_norm_history: list[float] = []

    def _reset_history(self) -> None:
        self.gradient_norm_history = []
        self.accel_norm_history = []

    @staticmethod
    def _accel_gradient(q: ArrayLike, a_hat: ArrayLike) -> ArrayF:
        w, x, y, z = so3.normalize_quat(q)
        ax, ay, az = _as_vec3(a_hat)
        f = np.array(
            [
                2.0 * (x * z - w * y) - ax,
                2.0 * (y * z + w * x) - ay,
                1.0 - 2.0 * (x * x + y * y) - az,
            ],
            dtype=np.float64,
        )
        jac = np.array(
            [
                [-2.0 * y, 2.0 * z, -2.0 * w, 2.0 * x],
                [2.0 * x, 2.0 * w, 2.0 * z, 2.0 * y],
                [0.0, -4.0 * x, -4.0 * y, 0.0],
            ],
            dtype=np.float64,
        )
        return jac.T @ f

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v = _as_vec3(gyro)
        accel_v = _as_vec3(accel)
        dt_s = _safe_dt(dt)
        q_prev = self.q.copy()
        q_dot = 0.5 * so3.quat_multiply(self.q, np.array([0.0, *gyro_v], dtype=np.float64))
        grad_norm = 0.0

        a_hat = _unit_or_none(accel_v)
        if a_hat is not None and self.beta > 0.0:
            grad = self._accel_gradient(self.q, a_hat)
            grad_norm = float(np.linalg.norm(grad))
            if grad_norm > 1e-12:
                q_dot -= self.beta * grad / grad_norm

        self.q = so3.normalize_quat(self.q + q_dot * dt_s)
        self.q = _sanitize_quat(self.q, q_prev)
        self.gradient_norm_history.append(grad_norm)
        self.accel_norm_history.append(float(np.linalg.norm(accel_v)))
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "beta": self.beta,
            "gradient_norm": np.asarray(self.gradient_norm_history, dtype=np.float64),
            "accel_norm": np.asarray(self.accel_norm_history, dtype=np.float64),
        }


class EKFOrientation(_EstimatorBase):
    """Error-state EKF with nominal quaternion and gyro bias.

    The covariance state is ``[delta_theta_body, gyro_bias]``. Accel updates use
    only the measured direction of specific force. Measurement noise is inflated
    as ``||accel||`` departs from ``g`` so high-dynamic swing samples are trusted
    less than quiet address/finish samples.
    """

    name = "ekf_orientation"

    def __init__(
        self,
        gyro_noise: float = 0.03,
        bias_rw: float = 0.001,
        accel_dir_noise: float = 0.05,
        accel_sigma: float = 2.0,
        max_noise_scale: float = 100.0,
        initial_attitude_std: float = 0.25,
        initial_bias_std: float = 0.2,
        initial_bias: ArrayLike | None = None,
        max_update_rad: float = 0.5,
    ) -> None:
        super().__init__()
        self.gyro_noise = float(gyro_noise)
        self.bias_rw = float(bias_rw)
        self.accel_dir_noise = float(accel_dir_noise)
        self.accel_sigma = float(accel_sigma)
        self.max_noise_scale = float(max_noise_scale)
        self.initial_attitude_std = float(initial_attitude_std)
        self.initial_bias_std = float(initial_bias_std)
        self.initial_bias = _as_vec3(initial_bias) if initial_bias is not None else np.zeros(3)
        self.max_update_rad = float(max_update_rad)
        self.bias = self.initial_bias.copy()
        self.P = np.eye(6, dtype=np.float64)
        self.bias_history: list[ArrayF] = []
        self.innovation_history: list[ArrayF] = []
        self.noise_scale_history: list[float] = []
        self.p_trace_history: list[float] = []
        self.accel_norm_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = self.initial_bias.copy()
        self.P = np.diag(
            [
                self.initial_attitude_std**2,
                self.initial_attitude_std**2,
                self.initial_attitude_std**2,
                self.initial_bias_std**2,
                self.initial_bias_std**2,
                self.initial_bias_std**2,
            ]
        ).astype(np.float64)

    def _reset_history(self) -> None:
        self.bias_history = []
        self.innovation_history = []
        self.noise_scale_history = []
        self.p_trace_history = []
        self.accel_norm_history = []

    def _propagate_covariance(self, omega: ArrayF, dt_s: float) -> None:
        F = np.eye(6, dtype=np.float64)
        F[:3, :3] -= _skew(omega) * dt_s
        F[:3, 3:] = -np.eye(3) * dt_s
        q_theta = max(self.gyro_noise, 0.0) ** 2 * dt_s * dt_s
        q_bias = max(self.bias_rw, 0.0) ** 2 * dt_s
        Q = np.diag([q_theta, q_theta, q_theta, q_bias, q_bias, q_bias]).astype(np.float64)
        self.P = F @ self.P @ F.T + Q
        self.P = 0.5 * (self.P + self.P.T)

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v = _as_vec3(gyro)
        accel_v = _as_vec3(accel)
        dt_s = _safe_dt(dt)
        q_prev = self.q.copy()

        omega = gyro_v - self.bias
        self.q = so3.integrate_gyro_rk4(self.q, omega, dt_s)
        self._propagate_covariance(omega, dt_s)

        innovation = np.zeros(3, dtype=np.float64)
        noise_scale = 0.0
        a_norm = float(np.linalg.norm(accel_v))
        z = _unit_or_none(accel_v)
        if z is not None:
            h = _predicted_up_body(self.q)
            innovation = z - h
            H = np.zeros((3, 6), dtype=np.float64)
            H[:, :3] = _skew(h)
            sigma = max(self.accel_sigma, 1e-6)
            noise_scale = 1.0 + ((a_norm - G_NORM) / sigma) ** 2
            noise_scale = float(np.clip(noise_scale, 1.0, max(self.max_noise_scale, 1.0)))
            meas_var = max(self.accel_dir_noise, 1e-6) ** 2 * noise_scale
            Rm = np.eye(3, dtype=np.float64) * meas_var
            S = H @ self.P @ H.T + Rm
            PHt = self.P @ H.T
            try:
                K = np.linalg.solve(S.T, PHt.T).T
            except np.linalg.LinAlgError:
                K = PHt @ np.linalg.pinv(S)
            dx = K @ innovation
            dtheta = dx[:3]
            dtheta_norm = float(np.linalg.norm(dtheta))
            if dtheta_norm > self.max_update_rad > 0.0:
                dtheta *= self.max_update_rad / dtheta_norm
            self.q = so3.normalize_quat(so3.quat_multiply(self.q, _small_angle_quat(dtheta)))
            self.bias += dx[3:]

            I = np.eye(6, dtype=np.float64)
            IKH = I - K @ H
            self.P = IKH @ self.P @ IKH.T + K @ Rm @ K.T
            self.P = 0.5 * (self.P + self.P.T)

        self.q = _sanitize_quat(self.q, q_prev)
        self.bias_history.append(self.bias.copy())
        self.innovation_history.append(innovation.copy())
        self.noise_scale_history.append(noise_scale)
        self.p_trace_history.append(float(np.trace(self.P)))
        self.accel_norm_history.append(a_norm)
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "gyro_noise": self.gyro_noise,
            "bias_rw": self.bias_rw,
            "accel_dir_noise": self.accel_dir_noise,
            "accel_sigma": self.accel_sigma,
            "bias": np.asarray(self.bias_history, dtype=np.float64),
            "innovation": np.asarray(self.innovation_history, dtype=np.float64),
            "measurement_noise_scale": np.asarray(self.noise_scale_history, dtype=np.float64),
            "cov_trace": np.asarray(self.p_trace_history, dtype=np.float64),
            "accel_norm": np.asarray(self.accel_norm_history, dtype=np.float64),
        }


class GatedAdaptive(_EstimatorBase):
    """Golf-specific smooth-gated accel tilt correction with rest bias learning."""

    name = "gated_adaptive"

    def __init__(
        self,
        tilt_gain: float = 3.0,
        sigma_a: float = 2.5,
        sigma_w: float = 8.0,
        bias_tau_s: float = 0.5,
        rest_accel_tol_g: float = 0.06,
        rest_gyro_thresh: float = 0.25,
        initial_bias: ArrayLike | None = None,
    ) -> None:
        super().__init__()
        self.tilt_gain = float(tilt_gain)
        self.sigma_a = float(sigma_a)
        self.sigma_w = float(sigma_w)
        self.bias_tau_s = float(bias_tau_s)
        self.rest_accel_tol_g = float(rest_accel_tol_g)
        self.rest_gyro_thresh = float(rest_gyro_thresh)
        self.initial_bias = _as_vec3(initial_bias) if initial_bias is not None else np.zeros(3)
        self.bias = self.initial_bias.copy()
        self.bias_history: list[ArrayF] = []
        self.gain_history: list[float] = []
        self.alpha_history: list[float] = []
        self.dynamic_scale_history: list[float] = []
        self.rest_history: list[bool] = []
        self.accel_norm_history: list[float] = []
        self.gyro_norm_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = self.initial_bias.copy()

    def _reset_history(self) -> None:
        self.bias_history = []
        self.gain_history = []
        self.alpha_history = []
        self.dynamic_scale_history = []
        self.rest_history = []
        self.accel_norm_history = []
        self.gyro_norm_history = []

    def _dynamic_scale(self, gyro_norm: float, accel_norm: float) -> float:
        if accel_norm < 1e-9:
            return 0.0
        sigma_a = max(self.sigma_a, 1e-6)
        sigma_w = max(self.sigma_w, 1e-6)
        accel_term = np.exp(-((accel_norm - G_NORM) / sigma_a) ** 2)
        gyro_term = np.exp(-(gyro_norm / sigma_w) ** 2)
        return float(np.clip(accel_term * gyro_term, 0.0, 1.0))

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v = _as_vec3(gyro)
        accel_v = _as_vec3(accel)
        dt_s = _safe_dt(dt)
        q_prev = self.q.copy()
        accel_norm = float(np.linalg.norm(accel_v))
        gyro_norm = float(np.linalg.norm(gyro_v))
        rest = (
            abs(accel_norm - G_NORM) <= self.rest_accel_tol_g * G_NORM
            and gyro_norm <= self.rest_gyro_thresh
        )

        if rest and self.bias_tau_s > 0.0 and dt_s > 0.0:
            bias_alpha = 1.0 - float(np.exp(-dt_s / self.bias_tau_s))
            self.bias += bias_alpha * (gyro_v - self.bias)

        q_pred = so3.integrate_gyro_rk4(self.q, gyro_v - self.bias, dt_s)
        dynamic_scale = self._dynamic_scale(gyro_norm, accel_norm)
        effective_gain = max(self.tilt_gain, 0.0) * dynamic_scale
        alpha = 1.0 - float(np.exp(-effective_gain * dt_s))
        self.q = _apply_world_tilt_correction(q_pred, accel_v, alpha)
        self.q = _sanitize_quat(self.q, q_prev)

        self.bias_history.append(self.bias.copy())
        self.gain_history.append(effective_gain)
        self.alpha_history.append(alpha)
        self.dynamic_scale_history.append(dynamic_scale)
        self.rest_history.append(bool(rest))
        self.accel_norm_history.append(accel_norm)
        self.gyro_norm_history.append(gyro_norm)
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "tilt_gain": self.tilt_gain,
            "sigma_a": self.sigma_a,
            "sigma_w": self.sigma_w,
            "bias_tau_s": self.bias_tau_s,
            "bias": np.asarray(self.bias_history, dtype=np.float64),
            "gain_history": np.asarray(self.gain_history, dtype=np.float64),
            "alpha_history": np.asarray(self.alpha_history, dtype=np.float64),
            "dynamic_scale": np.asarray(self.dynamic_scale_history, dtype=np.float64),
            "rest_mask": np.asarray(self.rest_history, dtype=bool),
            "accel_norm": np.asarray(self.accel_norm_history, dtype=np.float64),
            "gyro_norm": np.asarray(self.gyro_norm_history, dtype=np.float64),
        }


def rts_smooth_orientations(
    quats: ArrayLike,
    alpha: float = 0.25,
    blend: float = 0.5,
    passes: int = 1,
) -> ArrayF:
    """Forward-backward quaternion low-pass smoother.

    This is intentionally lightweight and is not a true Rauch-Tung-Striebel
    smoother because it has no process model or covariance. It is useful for
    visualization or post-processing benchmark traces after filtering. For
    physically meaningful smoothing, prefer ``forward_backward_filter_smooth``
    with a configured estimator and the original gyro/accel samples.
    """

    qs = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    if qs.shape[0] == 0:
        return np.zeros((0, 4), dtype=np.float64)
    out = np.zeros_like(qs, dtype=np.float64)
    out[0] = _sanitize_quat(qs[0])
    for i in range(1, qs.shape[0]):
        out[i] = _sanitize_quat(qs[i], out[i - 1])

    alpha = float(np.clip(alpha, 0.0, 1.0))
    blend = float(np.clip(blend, 0.0, 1.0))
    num_passes = max(int(passes), 1)
    for _ in range(num_passes):
        fwd = np.zeros_like(out)
        bwd = np.zeros_like(out)
        fwd[0] = out[0]
        for i in range(1, out.shape[0]):
            fwd[i] = quat_slerp(fwd[i - 1], out[i], alpha)
        bwd[-1] = out[-1]
        for i in range(out.shape[0] - 2, -1, -1):
            bwd[i] = quat_slerp(bwd[i + 1], out[i], alpha)
        for i in range(out.shape[0]):
            out[i] = quat_slerp(fwd[i], bwd[i], blend)
            if i > 0:
                out[i] = _sanitize_quat(out[i], out[i - 1])
    return out


def forward_backward_filter_smooth(
    estimator_factory: Callable[[], OrientationEstimator],
    gyro_seq: ArrayLike,
    accel_seq: ArrayLike,
    dt: float | ArrayLike,
    q0: ArrayLike | None = None,
    blend: float = 0.5,
) -> tuple[ArrayF, dict[str, Any]]:
    """Run an estimator forward and backward, then SLERP-blend both traces.

    The backward pass uses time-reversed accel and negated time-reversed gyro.
    This assumes the estimator is approximately reversible under gyro sign
    change; adaptive bias states and nonlinear accel correction make it an
    approximation rather than an optimal smoother.
    """

    gyros, accels, dts = _prepare_sequences(gyro_seq, accel_seq, dt)
    if gyros.shape[0] == 0:
        return np.zeros((0, 4), dtype=np.float64), {
            "forward": {},
            "backward": {},
            "method": "forward_backward_filter_smooth",
        }

    fwd_est = estimator_factory()
    q_fwd, diag_fwd = fwd_est.run(gyros, accels, dts, q0=q0)

    bwd_est = estimator_factory()
    q_bwd_rev, diag_bwd = bwd_est.run(
        -gyros[::-1],
        accels[::-1],
        dts[::-1],
        q0=q_fwd[-1],
    )
    q_bwd = q_bwd_rev[::-1].copy()
    for i in range(q_bwd.shape[0] - 2, -1, -1):
        q_bwd[i] = _sanitize_quat(q_bwd[i], q_bwd[i + 1])

    blend = float(np.clip(blend, 0.0, 1.0))
    smooth = np.zeros_like(q_fwd)
    for i in range(q_fwd.shape[0]):
        smooth[i] = quat_slerp(q_fwd[i], q_bwd[i], blend)
        if i > 0:
            smooth[i] = _sanitize_quat(smooth[i], smooth[i - 1])

    diagnostics = {
        "method": "forward_backward_filter_smooth",
        "blend": blend,
        "forward": diag_fwd,
        "backward": diag_bwd,
    }
    return smooth, diagnostics


def make_default_suite() -> list[OrientationEstimator]:
    """Construct a conservative default set for benchmarking."""

    return [
        GyroOnly(),
        Complementary(gain=2.0),
        MahonyAHRS(kp=2.0, ki=0.05),
        MadgwickAHRS(beta=0.1),
        EKFOrientation(),
        GatedAdaptive(),
    ]
