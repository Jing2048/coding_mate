"""Orientation-estimation filter suite for head-to-head benchmarking.

Conventions
-----------
* quaternions are scalar-first ``[w, x, y, z]`` mapping body vectors to world
* gyro is body angular rate in rad/s, accel is specific force in m/s^2
* world gravity is ``G_WORLD = [0, 0, -9.80665]``
* at rest ``a_meas ~= -R(q).T @ G_WORLD``

Yaw is unobservable for 6-axis filters: accelerometer updates constrain tilt
only, so heading is whatever gyro integration produces. Every metric derived
downstream is therefore expressed relative to the address pose.
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
    name: str

    def reset(self, q0: ArrayLike | None = None) -> None: ...

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF: ...

    def run(
        self,
        gyro_seq: ArrayLike,
        accel_seq: ArrayLike,
        dt: float | ArrayLike,
        q0: ArrayLike | None = None,
    ) -> tuple[ArrayF, dict[str, Any]]: ...


@dataclass(frozen=True)
class FilterTuningSummary:
    filter_name: str
    parameters: str
    strengths: str
    weaknesses: str


TUNING_TABLE: tuple[FilterTuningSummary, ...] = (
    FilterTuningSummary(
        "GyroOnly",
        "none",
        "Best short-window dynamic fidelity when bias is removed; no accel contamination.",
        "Unbounded drift; cannot recover a wrong initial tilt.",
    ),
    FilterTuningSummary(
        "Complementary",
        "gain (1/s)",
        "Simple deterministic baseline; good during quiet address and finish.",
        "Fixed accel trust, so impact and centripetal terms corrupt tilt.",
    ),
    FilterTuningSummary(
        "MahonyAHRS",
        "kp, ki",
        "Bias-aware SO(3) complementary filter; cheap and robust.",
        "Integral term can be dragged by sustained non-gravity acceleration.",
    ),
    FilterTuningSummary(
        "MadgwickAHRS",
        "beta",
        "Widely used 6-axis baseline; tolerant of large initial tilt error.",
        "Single gain trades convergence against high-dynamic accel sensitivity.",
    ),
    FilterTuningSummary(
        "EKFOrientation",
        "gyro_noise, bias_rw, accel_dir_noise, accel_sigma",
        "Principled covariance and bias tracking; accel trust falls off smoothly.",
        "More tuning and compute; yaw stays weakly observable without a magnetometer.",
    ),
    FilterTuningSummary(
        "GatedAdaptive",
        "tilt_gain, sigma_a, sigma_w, bias_tau_s",
        "Golf-specific smooth accel gating plus rest-only bias learning.",
        "Needs sigma tuning per sensor/club; no full covariance model.",
    ),
)


def _as_vec3(x: ArrayLike) -> ArrayF:
    v = np.asarray(x, dtype=np.float64).reshape(3)
    return np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)


def _safe_dt(dt: float) -> float:
    return max(float(np.nan_to_num(dt, nan=0.0, posinf=0.0, neginf=0.0)), 0.0)


def _sanitize_quat(q: ArrayLike, ref: ArrayLike | None = None) -> ArrayF:
    q_arr = np.nan_to_num(
        np.asarray(q, dtype=np.float64).reshape(4), nan=0.0, posinf=0.0, neginf=0.0
    )
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


def _skew(v: ArrayLike) -> ArrayF:
    x, y, z = _as_vec3(v)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)


@dataclass
class DynamicsGate:
    """Trust factor in [0, 1] for using the accelerometer as a gravity reference.

    Magnitude alone is not sufficient. At the top of the backswing the angular
    rate passes through zero and the specific force can sit close to ``g``, yet
    the accelerometer is dominated by the tangential term ``r * alpha`` because
    the swing is reversing. A gate that only watches ``|a| - g`` and ``|w|``
    therefore opens at exactly the worst moment. Including angular acceleration
    closes it, since ``alpha`` peaks at the reversal.

    Scales are deliberately tight. Over a one-second swing the gyro integrates
    accurately, so an over-eager accelerometer update costs far more than the
    drift it removes; the accelerometer earns its keep in the quiet address and
    finish windows, not mid-swing.
    """

    sigma_a: float = 0.5  # m/s^2 of specific-force anomaly
    sigma_w: float = 0.8  # rad/s
    sigma_alpha: float = 5.0  # rad/s^2

    def __call__(self, gyro_norm: float, accel_norm: float, alpha_norm: float) -> float:
        if accel_norm < 1e-9:
            return 0.0
        a_term = np.exp(-(((accel_norm - G_NORM) / max(self.sigma_a, 1e-6)) ** 2))
        w_term = np.exp(-((gyro_norm / max(self.sigma_w, 1e-6)) ** 2))
        al_term = np.exp(-((alpha_norm / max(self.sigma_alpha, 1e-6)) ** 2))
        return float(np.clip(a_term * w_term * al_term, 0.0, 1.0))


def _predicted_up_body(q: ArrayLike) -> ArrayF:
    return (-so3.quat_to_rotmat(q).T @ so3.G_WORLD) / G_NORM


def quat_slerp(q0: ArrayLike, q1: ArrayLike, t: float) -> ArrayF:
    t = float(np.clip(t, 0.0, 1.0))
    qa, qb = _sanitize_quat(q0), _sanitize_quat(q1)
    dot = float(np.dot(qa, qb))
    if dot < 0.0:
        qb, dot = -qb, -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        return so3.normalize_quat(qa + t * (qb - qa))
    theta = float(np.arccos(dot))
    s = float(np.sin(theta))
    if abs(s) < 1e-12:
        return qa.copy()
    return so3.normalize_quat(
        (np.sin((1.0 - t) * theta) / s) * qa + (np.sin(t * theta) / s) * qb
    )


def _small_angle_quat(delta: ArrayLike) -> ArrayF:
    delta = _as_vec3(delta)
    angle = float(np.linalg.norm(delta))
    if angle < 1e-12:
        return IDENTITY_QUAT.copy()
    return so3.quat_from_axis_angle(delta / angle, angle)


def _apply_world_tilt_correction(q: ArrayLike, accel: ArrayLike, alpha: float) -> ArrayF:
    """Yaw-free accel tilt correction applied by left multiplication in world."""
    alpha = float(np.clip(alpha, 0.0, 1.0))
    q_in = _sanitize_quat(q)
    if alpha <= 0.0:
        return q_in
    a_hat = _unit_or_none(accel)
    if a_hat is None:
        return q_in
    measured_up_world = so3.quat_to_rotmat(q_in) @ a_hat
    q_err = so3.quat_from_two_vectors(measured_up_world, UP_WORLD)
    return so3.normalize_quat(so3.quat_multiply(quat_slerp(IDENTITY_QUAT, q_err, alpha), q_in))


def _prepare(
    gyro_seq: ArrayLike, accel_seq: ArrayLike, dt: float | ArrayLike
) -> tuple[ArrayF, ArrayF, ArrayF]:
    gyros = np.nan_to_num(np.asarray(gyro_seq, dtype=np.float64).reshape(-1, 3))
    accels = np.nan_to_num(np.asarray(accel_seq, dtype=np.float64).reshape(-1, 3))
    if gyros.shape != accels.shape:
        raise ValueError("gyro_seq and accel_seq must have matching shape")
    n = gyros.shape[0]
    dt_arr = np.asarray(dt, dtype=np.float64)
    if dt_arr.ndim == 0:
        dts = np.full(n, _safe_dt(float(dt_arr)), dtype=np.float64)
    else:
        dts = np.maximum(np.nan_to_num(dt_arr.reshape(-1)), 0.0)
        if dts.shape[0] != n:
            raise ValueError("dt sequence length mismatch")
    return gyros, accels, dts


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
        gyros, accels, dts = _prepare(gyro_seq, accel_seq, dt)
        self.reset(q0)
        quats = np.zeros((gyros.shape[0], 4), dtype=np.float64)
        prev = self.q.copy()
        for i in range(gyros.shape[0]):
            q = self.update(gyros[i], accels[i], float(dts[i]))
            q = _sanitize_quat(q, prev)
            quats[i] = q
            self.q = q.copy()
            prev = q
        return quats, self.diagnostics()


class GyroOnly(_EstimatorBase):
    """Pure strapdown integration: drift reference and dynamic-fidelity ceiling."""

    name = "gyro_only"

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        del accel
        self.q = so3.integrate_gyro_rk4(self.q, _as_vec3(gyro), _safe_dt(dt))
        return self.q.copy()


class Complementary(_EstimatorBase):
    """Fixed-gain tilt complementary filter."""

    name = "complementary"

    def __init__(self, gain: float = 2.0) -> None:
        super().__init__()
        self.gain = float(gain)
        self.alpha_history: list[float] = []

    def _reset_history(self) -> None:
        self.alpha_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        dt_s = _safe_dt(dt)
        q_pred = so3.integrate_gyro_rk4(self.q, _as_vec3(gyro), dt_s)
        alpha = 1.0 - float(np.exp(-max(self.gain, 0.0) * dt_s))
        self.q = _apply_world_tilt_correction(q_pred, _as_vec3(accel), alpha)
        self.alpha_history.append(alpha)
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {"alpha_history": np.asarray(self.alpha_history, dtype=np.float64)}


class MahonyAHRS(_EstimatorBase):
    """Passive Mahony complementary filter on SO(3) with gyro-bias integral."""

    name = "mahony"

    def __init__(self, kp: float = 2.0, ki: float = 0.05) -> None:
        super().__init__()
        self.kp = float(kp)
        self.ki = float(ki)
        self.bias = np.zeros(3, dtype=np.float64)
        self.bias_history: list[ArrayF] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = np.zeros(3, dtype=np.float64)

    def _reset_history(self) -> None:
        self.bias_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v, dt_s = _as_vec3(gyro), _safe_dt(dt)
        error = np.zeros(3, dtype=np.float64)
        a_hat = _unit_or_none(accel)
        if a_hat is not None:
            error = np.cross(a_hat, _predicted_up_body(self.q))
            if self.ki > 0.0 and dt_s > 0.0:
                self.bias += -self.ki * error * dt_s
        self.q = so3.integrate_gyro_rk4(self.q, gyro_v - self.bias + self.kp * error, dt_s)
        self.bias_history.append(self.bias.copy())
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {"bias": np.asarray(self.bias_history, dtype=np.float64)}


class MadgwickAHRS(_EstimatorBase):
    """Madgwick 6-axis gradient-descent filter."""

    name = "madgwick"

    def __init__(self, beta: float = 0.1) -> None:
        super().__init__()
        self.beta = float(beta)

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
        dt_s = _safe_dt(dt)
        q_dot = 0.5 * so3.quat_multiply(
            self.q, np.array([0.0, *_as_vec3(gyro)], dtype=np.float64)
        )
        a_hat = _unit_or_none(accel)
        if a_hat is not None and self.beta > 0.0:
            grad = self._accel_gradient(self.q, a_hat)
            gn = float(np.linalg.norm(grad))
            if gn > 1e-12:
                q_dot -= self.beta * grad / gn
        self.q = so3.normalize_quat(self.q + q_dot * dt_s)
        return self.q.copy()


class EKFOrientation(_EstimatorBase):
    """Error-state EKF over [delta_theta, gyro_bias] with adaptive accel noise.

    Measurement noise is inflated as ``||a||`` departs from ``g``, which is the
    statistically principled version of hard accel gating.
    """

    name = "ekf"

    def __init__(
        self,
        gyro_noise: float = 0.03,
        bias_rw: float = 0.001,
        accel_dir_noise: float = 0.05,
        accel_sigma: float = 2.0,
        max_noise_scale: float = 1e6,
        max_update_rad: float = 0.5,
        gate: DynamicsGate | None = None,
    ) -> None:
        super().__init__()
        self.gyro_noise = float(gyro_noise)
        self.bias_rw = float(bias_rw)
        self.accel_dir_noise = float(accel_dir_noise)
        self.accel_sigma = float(accel_sigma)
        self.max_noise_scale = float(max_noise_scale)
        self.max_update_rad = float(max_update_rad)
        self.gate = gate or DynamicsGate()
        self.bias = np.zeros(3, dtype=np.float64)
        self.P = np.eye(6, dtype=np.float64)
        self._prev_gyro: ArrayF | None = None
        self.bias_history: list[ArrayF] = []
        self.noise_scale_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = np.zeros(3, dtype=np.float64)
        self.P = np.diag([0.0625, 0.0625, 0.0625, 0.04, 0.04, 0.04]).astype(np.float64)
        self._prev_gyro = None

    def _reset_history(self) -> None:
        self.bias_history = []
        self.noise_scale_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro_v, accel_v, dt_s = _as_vec3(gyro), _as_vec3(accel), _safe_dt(dt)
        alpha_norm = 0.0
        if self._prev_gyro is not None and dt_s > 0:
            alpha_norm = float(np.linalg.norm(gyro_v - self._prev_gyro) / dt_s)
        self._prev_gyro = gyro_v.copy()
        omega = gyro_v - self.bias
        self.q = so3.integrate_gyro_rk4(self.q, omega, dt_s)

        F = np.eye(6, dtype=np.float64)
        F[:3, :3] -= _skew(omega) * dt_s
        F[:3, 3:] = -np.eye(3) * dt_s
        q_theta = max(self.gyro_noise, 0.0) ** 2 * dt_s * dt_s
        q_bias = max(self.bias_rw, 0.0) ** 2 * dt_s
        self.P = F @ self.P @ F.T + np.diag([q_theta] * 3 + [q_bias] * 3)
        self.P = 0.5 * (self.P + self.P.T)

        noise_scale = 0.0
        z = _unit_or_none(accel_v)
        if z is not None:
            h = _predicted_up_body(self.q)
            innovation = z - h
            H = np.zeros((3, 6), dtype=np.float64)
            H[:, :3] = _skew(h)
            a_norm = float(np.linalg.norm(accel_v))
            trust = self.gate(float(np.linalg.norm(gyro_v)), a_norm, alpha_norm)
            noise_scale = float(
                np.clip(1.0 / max(trust, 1.0 / self.max_noise_scale), 1.0, self.max_noise_scale)
            )
            Rm = np.eye(3) * (max(self.accel_dir_noise, 1e-6) ** 2 * noise_scale)
            S = H @ self.P @ H.T + Rm
            PHt = self.P @ H.T
            try:
                K = np.linalg.solve(S.T, PHt.T).T
            except np.linalg.LinAlgError:
                K = PHt @ np.linalg.pinv(S)
            dx = K @ innovation
            dtheta = dx[:3]
            dn = float(np.linalg.norm(dtheta))
            if dn > self.max_update_rad > 0.0:
                dtheta = dtheta * (self.max_update_rad / dn)
            self.q = so3.normalize_quat(so3.quat_multiply(self.q, _small_angle_quat(dtheta)))
            self.bias += dx[3:]
            IKH = np.eye(6) - K @ H
            self.P = IKH @ self.P @ IKH.T + K @ Rm @ K.T
            self.P = 0.5 * (self.P + self.P.T)

        self.bias_history.append(self.bias.copy())
        self.noise_scale_history.append(noise_scale)
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "bias": np.asarray(self.bias_history, dtype=np.float64),
            "measurement_noise_scale": np.asarray(self.noise_scale_history, dtype=np.float64),
        }


class GatedAdaptive(_EstimatorBase):
    """Golf-specific filter: smooth accel trust plus rest-only bias learning.

    The accel correction gain is scaled by a product of Gaussian kernels in
    ``|a| - g`` and ``|w|``. Unlike a binary gate this is continuous, so there is
    no gain discontinuity at the threshold during the transition into downswing.
    """

    name = "gated_adaptive"

    def __init__(
        self,
        tilt_gain: float = 3.0,
        bias_tau_s: float = 0.5,
        rest_accel_tol_g: float = 0.06,
        rest_gyro_thresh: float = 0.25,
        gate: DynamicsGate | None = None,
        use_signed_log_tilt: bool = True,
        signed_log_scale: float = 9.80665,
    ) -> None:
        super().__init__()
        self.tilt_gain = float(tilt_gain)
        self.bias_tau_s = float(bias_tau_s)
        self.rest_accel_tol_g = float(rest_accel_tol_g)
        self.rest_gyro_thresh = float(rest_gyro_thresh)
        self.gate = gate or DynamicsGate()
        self.use_signed_log_tilt = bool(use_signed_log_tilt)
        self.signed_log_scale = float(signed_log_scale)
        self.bias = np.zeros(3, dtype=np.float64)
        self._prev_gyro: ArrayF | None = None
        self.gate_history: list[float] = []
        self.bias_history: list[ArrayF] = []
        self.rest_history: list[bool] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        super().reset(q0)
        self.bias = np.zeros(3, dtype=np.float64)
        self._prev_gyro = None

    def _reset_history(self) -> None:
        self.gate_history = []
        self.bias_history = []
        self.rest_history = []

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        from golfmate_algo.signal.dynamic_range import signed_log_compress

        gyro_v, accel_v, dt_s = _as_vec3(gyro), _as_vec3(accel), _safe_dt(dt)
        a_norm = float(np.linalg.norm(accel_v))
        w_norm = float(np.linalg.norm(gyro_v))
        alpha_norm = 0.0
        if self._prev_gyro is not None and dt_s > 0:
            alpha_norm = float(np.linalg.norm(gyro_v - self._prev_gyro) / dt_s)
        self._prev_gyro = gyro_v.copy()

        rest = (
            abs(a_norm - G_NORM) <= self.rest_accel_tol_g * G_NORM
            and w_norm <= self.rest_gyro_thresh
        )
        if rest and self.bias_tau_s > 0.0 and dt_s > 0.0:
            self.bias += (1.0 - float(np.exp(-dt_s / self.bias_tau_s))) * (gyro_v - self.bias)

        q_pred = so3.integrate_gyro_rk4(self.q, gyro_v - self.bias, dt_s)
        # Gate / rest from raw dynamics; tilt correction may use signed-log accel
        # so impact spikes do not yank the gravity reference.
        gate = self.gate(w_norm, a_norm, alpha_norm) if rest else 0.0
        alpha = 1.0 - float(np.exp(-max(self.tilt_gain, 0.0) * gate * dt_s))
        accel_tilt = (
            signed_log_compress(accel_v, scale=self.signed_log_scale)
            if self.use_signed_log_tilt
            else accel_v
        )
        self.q = _apply_world_tilt_correction(q_pred, accel_tilt, alpha)

        self.gate_history.append(gate)
        self.bias_history.append(self.bias.copy())
        self.rest_history.append(bool(rest))
        return self.q.copy()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "gate": np.asarray(self.gate_history, dtype=np.float64),
            "bias": np.asarray(self.bias_history, dtype=np.float64),
            "rest_mask": np.asarray(self.rest_history, dtype=bool),
        }


def forward_backward_smooth(
    factory: Callable[[], OrientationEstimator],
    gyro_seq: ArrayLike,
    accel_seq: ArrayLike,
    dt: float | ArrayLike,
    q0: ArrayLike | None = None,
    blend: float = 0.5,
) -> tuple[ArrayF, dict[str, Any]]:
    """Run an estimator forward and backward, then SLERP-blend the traces.

    The backward pass negates and reverses gyro. This is an approximation, not
    an optimal RTS smoother: adaptive bias states are not time-reversible.
    """
    gyros, accels, dts = _prepare(gyro_seq, accel_seq, dt)
    if gyros.shape[0] == 0:
        return np.zeros((0, 4), dtype=np.float64), {}

    q_fwd, diag_f = factory().run(gyros, accels, dts, q0=q0)
    q_rev, diag_b = factory().run(-gyros[::-1], accels[::-1], dts[::-1], q0=q_fwd[-1])
    q_bwd = q_rev[::-1].copy()
    for i in range(q_bwd.shape[0] - 2, -1, -1):
        q_bwd[i] = _sanitize_quat(q_bwd[i], q_bwd[i + 1])

    out = np.zeros_like(q_fwd)
    for i in range(q_fwd.shape[0]):
        out[i] = quat_slerp(q_fwd[i], q_bwd[i], float(np.clip(blend, 0.0, 1.0)))
        if i > 0:
            out[i] = _sanitize_quat(out[i], out[i - 1])
    return out, {"forward": diag_f, "backward": diag_b}


def make_default_suite() -> list[OrientationEstimator]:
    return [
        GyroOnly(),
        Complementary(gain=2.0),
        MahonyAHRS(kp=2.0, ki=0.05),
        MadgwickAHRS(beta=0.1),
        EKFOrientation(),
        GatedAdaptive(),
    ]
