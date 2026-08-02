"""Golf-specific gated AHRS: VQF 6D when available, complementary fallback otherwise."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.math import so3

ArrayF = NDArray[np.float64]

try:
    from vqf import VQF

    _HAS_VQF = True
except Exception:  # pragma: no cover - optional dependency path
    VQF = None  # type: ignore
    _HAS_VQF = False


@dataclass
class GateParams:
    """Accel tilt-correction gate for high-dynamic golf swings.

    When ||a|| differs from g by more than ``accel_tol_g * g`` OR ||ω|| exceeds
    ``omega_hi_rad_s``, accel correction is disabled (SciRep 2024 rationale).
    """

    accel_tol_g: float = 0.25
    omega_hi_rad_s: float = 2.5
    g: float = 9.80665
    # complementary fallback gains when gate open
    kp_tilt: float = 0.8


class ComplementaryGatedAHRS:
    """Pure-numpy gated complementary filter (testable without VQF)."""

    def __init__(self, params: GateParams | None = None) -> None:
        self.params = params or GateParams()
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self.gate_open_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        self.q = (
            so3.normalize_quat(q0)
            if q0 is not None
            else np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        )
        self.gate_open_history.clear()

    def _gate(self, gyro: ArrayF, accel: ArrayF) -> float:
        g = self.params.g
        an = float(np.linalg.norm(accel))
        wn = float(np.linalg.norm(gyro))
        accel_ok = abs(an - g) <= self.params.accel_tol_g * g
        omega_ok = wn <= self.params.omega_hi_rad_s
        return 1.0 if (accel_ok and omega_ok) else 0.0

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        gyro = np.asarray(gyro, dtype=np.float64).reshape(3)
        accel = np.asarray(accel, dtype=np.float64).reshape(3)
        gate = self._gate(gyro, accel)
        self.gate_open_history.append(gate)

        # Strapdown integrate gyro
        q_pred = so3.integrate_gyro_rk4(self.q, gyro, dt)

        if gate > 0.0 and np.linalg.norm(accel) > 1e-6:
            # Measured gravity direction in body frame (specific force ≈ -g_body when static)
            # With a_meas ≈ R^T * (-g_world) when stationary in NED-like z-down? We use
            # world gravity G_WORLD = [0,0,-g], so specific force when static is +g in sensor
            # if accelerometer reports proper acceleration reacting to gravity as +g upward
            # convention: a_static ≈ -R^T g_world = R^T [0,0,g] when g_world=[0,0,-g]
            a_hat = accel / (np.linalg.norm(accel) + 1e-12)
            # Predicted gravity direction in body (unit): R^T * [0,0,-1] = third row of R? 
            # rotate_vector maps body→world; gravity in body = R^T g_world
            R = so3.quat_to_rotmat(q_pred)
            g_body = R.T @ so3.G_WORLD
            g_body_hat = g_body / (np.linalg.norm(g_body) + 1e-12)
            # specific force when static should align with -g_body (accelerometer reads opposite to g)
            # Standard IMU: in level rest, accel ≈ [0,0,g] if z-up body with g_world=[0,0,-g]
            # Our G_WORLD=[0,0,-g]; R=I ⇒ g_body=[0,0,-g]; accel rest ≈ -g_body = [0,0,g]
            a_target = -g_body_hat
            # error rotation taking predicted a_target toward measured a_hat
            q_err = so3.quat_from_two_vectors(a_target, a_hat)
            # small correction: slerp-like blend on quaternion error
            # q_corr = q_err^α ≈ [1, α*v] for small; use power on angle
            angle = so3.geodesic_distance(np.array([1.0, 0.0, 0.0, 0.0]), q_err)
            alpha = float(np.clip(self.params.kp_tilt * dt * gate, 0.0, 1.0))
            if angle > 1e-10:
                q_corr = so3.quat_from_axis_angle(
                    so3.as_quat(q_err)[1:], angle * alpha
                ) if np.linalg.norm(q_err[1:]) > 1e-12 else np.array(
                    [1.0, 0.0, 0.0, 0.0], dtype=np.float64
                )
                # Better: interpolate identity → q_err
                q_corr = _quat_slerp(
                    np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64), q_err, alpha
                )
                q_pred = so3.normalize_quat(so3.quat_multiply(q_corr, q_pred))

        self.q = so3.ensure_quat_hemisphere(q_pred, self.q)
        return self.q.copy()

    def batch_process(
        self, gyros: ArrayLike, accels: ArrayLike, dt: float
    ) -> tuple[ArrayF, ArrayF]:
        gyros = np.asarray(gyros, dtype=np.float64).reshape(-1, 3)
        accels = np.asarray(accels, dtype=np.float64).reshape(-1, 3)
        n = gyros.shape[0]
        quats = np.zeros((n, 4), dtype=np.float64)
        for i in range(n):
            quats[i] = self.update(gyros[i], accels[i], dt)
        gate = np.asarray(self.gate_open_history[-n:], dtype=np.float64)
        return quats, gate


def _quat_slerp(q0: ArrayF, q1: ArrayF, t: float) -> ArrayF:
    q0 = so3.normalize_quat(q0)
    q1 = so3.normalize_quat(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        return so3.normalize_quat(q0 + t * (q1 - q0))
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    s = np.sin(theta)
    a = np.sin((1.0 - t) * theta) / s
    b = np.sin(t * theta) / s
    return so3.normalize_quat(a * q0 + b * q1)


class VQFGatedAHRS:
    """VQF 6D with post-hoc gate logging; during high dynamics freeze tilt by feeding
    synthetic gravity-aligned accel so VQF inclination correction is neutralized.
    """

    def __init__(self, gyr_ts: float, params: GateParams | None = None) -> None:
        if not _HAS_VQF:
            raise RuntimeError("vqf is not installed")
        self.params = params or GateParams()
        self.gyr_ts = float(gyr_ts)
        self._vqf = VQF(gyrTs=self.gyr_ts, accTs=self.gyr_ts)
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self.gate_open_history: list[float] = []

    def reset(self, q0: ArrayLike | None = None) -> None:
        self._vqf = VQF(gyrTs=self.gyr_ts, accTs=self.gyr_ts)
        self.gate_open_history.clear()
        if q0 is not None:
            self.q = so3.normalize_quat(q0)
        else:
            self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)

    def _gate(self, gyro: ArrayF, accel: ArrayF) -> float:
        g = self.params.g
        an = float(np.linalg.norm(accel))
        wn = float(np.linalg.norm(gyro))
        accel_ok = abs(an - g) <= self.params.accel_tol_g * g
        omega_ok = wn <= self.params.omega_hi_rad_s
        return 1.0 if (accel_ok and omega_ok) else 0.0

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        del dt  # VQF uses configured sample time
        gyro = np.asarray(gyro, dtype=np.float64).reshape(3)
        accel = np.asarray(accel, dtype=np.float64).reshape(3)
        gate = self._gate(gyro, accel)
        self.gate_open_history.append(gate)

        if gate < 0.5:
            # Neutralize accel correction: feed predicted gravity specific force
            R = so3.quat_to_rotmat(self.q)
            accel_use = -R.T @ so3.G_WORLD
        else:
            accel_use = accel

        self._vqf.update(gyro, accel_use)
        # VQF quat is [w,x,y,z]
        out = np.asarray(self._vqf.getQuat6D(), dtype=np.float64).reshape(4)
        self.q = so3.ensure_quat_hemisphere(so3.normalize_quat(out), self.q)
        return self.q.copy()

    def batch_process(
        self, gyros: ArrayLike, accels: ArrayLike, dt: float
    ) -> tuple[ArrayF, ArrayF]:
        gyros = np.asarray(gyros, dtype=np.float64).reshape(-1, 3)
        accels = np.asarray(accels, dtype=np.float64).reshape(-1, 3)
        n = gyros.shape[0]
        quats = np.zeros((n, 4), dtype=np.float64)
        for i in range(n):
            quats[i] = self.update(gyros[i], accels[i], dt)
        gate = np.asarray(self.gate_open_history[-n:], dtype=np.float64)
        return quats, gate


class GolfGatedAHRS:
    """Public AHRS facade: prefer VQF 6D, else complementary fallback."""

    def __init__(
        self,
        fs_hz: float,
        params: GateParams | None = None,
        prefer_vqf: bool = True,
    ) -> None:
        self.fs_hz = float(fs_hz)
        self.params = params or GateParams()
        self.backend_name: str
        if prefer_vqf and _HAS_VQF:
            self._impl: ComplementaryGatedAHRS | VQFGatedAHRS = VQFGatedAHRS(
                gyr_ts=1.0 / self.fs_hz, params=self.params
            )
            self.backend_name = "vqf6d"
        else:
            self._impl = ComplementaryGatedAHRS(params=self.params)
            self.backend_name = "complementary"

    @property
    def gate_open_history(self) -> list[float]:
        return self._impl.gate_open_history

    @property
    def q(self) -> ArrayF:
        return self._impl.q

    def reset(self, q0: ArrayLike | None = None) -> None:
        self._impl.reset(q0)

    def update(self, gyro: ArrayLike, accel: ArrayLike, dt: float) -> ArrayF:
        return self._impl.update(gyro, accel, dt)

    def batch_process(
        self, gyros: ArrayLike, accels: ArrayLike, dt: float | None = None
    ) -> tuple[ArrayF, ArrayF]:
        if dt is None:
            dt = 1.0 / self.fs_hz
        return self._impl.batch_process(gyros, accels, dt)


def gravity_remove(quats: ArrayLike, accels: ArrayLike) -> ArrayF:
    """Return linear acceleration in world frame: R * a_meas + g_world.

    With a_meas ≈ -R^T g when static ⇒ lin ≈ 0.
    """
    quats = np.asarray(quats, dtype=np.float64).reshape(-1, 4)
    accels = np.asarray(accels, dtype=np.float64).reshape(-1, 3)
    n = quats.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quats[i])
        out[i] = R @ accels[i] + so3.G_WORLD
    return out


HAS_VQF = _HAS_VQF
