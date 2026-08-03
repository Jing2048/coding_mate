"""Physics-grade multibody golf-swing simulator producing exact ground truth.

This module synthesises a golf swing as a driven serial kinematic chain of four
rigid segments -- pelvis, torso, lead arm and club -- and emits *analytic*
ground truth for every quantity an IMU algorithm might need to be graded
against: per-segment orientation / angular velocity / angular acceleration, the
world-frame position / velocity / acceleration of a rigidly mounted wrist
sensor (including its lever-arm centripetal / tangential / Euler terms), the
club-head trajectory and speed, and the exact specific force + gyro the sensor
would measure.

Design goals
------------
* **Exactness.** All driving signals are built from scaled Beta "bumps" whose
  time integral (segment angle) and time derivative (angular acceleration) are
  available in closed form via :func:`scipy.special.betainc`. Beta bumps have
  compact support, so the address hold, the top of the backswing and the finish
  hold are *exactly* static / stationary by construction, and every event index
  is exact. Rigid-body kinematics are then propagated with the exact moving-frame
  recursion, so the reported accelerometer / gyro are consistent with the
  reported position trajectory to numerical precision. :func:`self_consistency`
  re-derives everything by numerical differentiation / gyro re-integration and
  reports the residuals.

* **Biomechanical fidelity.** The four segments are driven so their angular
  speeds peak in the proximal-to-distal order pelvis -> torso -> arm -> club
  (the "kinematic sequence"). Peak magnitudes and peak times are fully
  configurable so both a healthy sequence and pathological ones (e.g. an
  out-of-order "casting" release) can be synthesised. The swing is planar in an
  inclined swing plane whose tilt from the horizontal is configurable
  (default 55 deg), while the orientations are genuinely 3D.

Conventions (shared with the rest of :mod:`golfmate_algo`)
----------------------------------------------------------
* Quaternions are ``[w, x, y, z]`` (scalar-first), unit norm, float64, mapping
  body -> world.
* World gravity vector is ``g_world = [0, 0, -9.80665]`` m/s^2 (``so3.G_WORLD``).
* Gyroscope in rad/s, accelerometer (specific force) in m/s^2, time in seconds.
* Specific force at the sensor is ``f_body = R_sensor^T (a_sensor_world - g_world)``
  so that a static, level sensor reads ``[0, 0, +9.80665]``.

Key equations
-------------
For a single fixed rotation axis ``n`` (the swing-plane normal) and a segment
cumulative plane angle ``Phi_i(t)``:

    R_i(t)          = Rodrigues(n, Phi_i(t))                     (body->world)
    omega_i^world   = n * Phi_i_dot(t)                           (segment ang. vel.)
    alpha_i^world   = n * Phi_i_ddot(t)                          (segment ang. acc.)

with ``Phi_i = sum_{j<=i} theta_j`` the sum of the driven joint angles (this is
exactly the biomechanical statement that a distal segment's speed is the sum of
the proximal joint speeds). Serial-chain origins ``O_i`` (``O_0`` fixed) and the
sensor point ``p_s = O_m + R_m r`` propagate by the moving-frame recursion:

    O_{i+1} = O_i + R_i d_i
    v_{i+1} = v_i + omega_i x (R_i d_i)
    a_{i+1} = a_i + alpha_i x (R_i d_i) + omega_i x (omega_i x (R_i d_i))
    v_s     = v_{O_m} + omega_m x (R_m r)
    a_s     = a_{O_m} + alpha_m x (R_m r) + omega_m x (omega_m x (R_m r))

The measured signals are ``gyro = R_sensor^T omega_m`` and
``accel = R_sensor^T (a_s - g_world)`` with ``R_sensor = R_m R_ext``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import beta as _beta_func
from scipy.special import betainc as _betainc

from golfmate_algo.math import so3
from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]

_DEG: float = np.pi / 180.0
_RAD2DEG: float = 180.0 / np.pi

SEGMENT_NAMES: tuple[str, str, str, str] = ("pelvis", "torso", "lead_arm", "club")

__all__ = [
    "BetaBump",
    "SegmentGeometry",
    "SwingConfig",
    "SwingTruth",
    "build_swing",
    "casting_swing",
    "self_consistency",
    "SEGMENT_NAMES",
]


# ---------------------------------------------------------------------------
# Driving-profile primitive: a compactly-supported, C2, analytically-integrable
# angular-velocity bump.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BetaBump:
    """A scaled Beta-shaped angular-velocity pulse on ``[t0, t1]``.

    The pulse shape is ``g(s) = s**p * (1 - s)**q`` for ``s = (t - t0) / (t1 - t0)``
    in ``[0, 1]`` and zero elsewhere. With ``p >= 3`` and ``q >= 3`` the shape and
    its first two derivatives vanish at both ends, so the resulting angular
    velocity is ``C2`` and has *compact support* (exactly zero outside the
    window). The rate is normalised so that its extremum equals ``peak_rate``
    (signed, rad/s) at the shape peak ``s* = p / (p + q)``.

    Because ``g`` is a Beta kernel, both the antiderivative (the swept angle) and
    the derivative (the angular acceleration) are available in closed form:

        angle(t)  = peak_rate / g(s*) * T * B(p+1, q+1) * I_s(p+1, q+1)
        accel(t)  = peak_rate / g(s*) * g'(s) / T

    where ``T = t1 - t0``, ``B`` is the Beta function and ``I_s`` is the
    regularised incomplete Beta function (``scipy.special.betainc``).
    """

    t0: float
    t1: float
    p: float
    q: float
    peak_rate: float

    def __post_init__(self) -> None:
        if self.t1 <= self.t0:
            raise ValueError("BetaBump requires t1 > t0")
        if self.p < 3.0 or self.q < 3.0:
            raise ValueError("BetaBump requires p >= 3 and q >= 3 for C2 support")

    @property
    def peak_time(self) -> float:
        """Absolute time at which the bump rate reaches ``peak_rate``."""
        s_star = self.p / (self.p + self.q)
        return self.t0 + s_star * (self.t1 - self.t0)

    @property
    def swept_angle(self) -> float:
        """Total angle (rad) accumulated over the whole bump window."""
        s_star = self.p / (self.p + self.q)
        g_star = (s_star**self.p) * ((1.0 - s_star) ** self.q)
        return (
            self.peak_rate / g_star * (self.t1 - self.t0) * _beta_func(self.p + 1.0, self.q + 1.0)
        )

    def _s(self, t: ArrayF) -> ArrayF:
        return (t - self.t0) / (self.t1 - self.t0)

    def rate(self, t: ArrayF) -> ArrayF:
        """Angular velocity contribution (rad/s), zero outside the window."""
        s = self._s(t)
        inside = (s >= 0.0) & (s <= 1.0)
        sc = np.clip(s, 0.0, 1.0)
        s_star = self.p / (self.p + self.q)
        g_star = (s_star**self.p) * ((1.0 - s_star) ** self.q)
        g = (sc**self.p) * ((1.0 - sc) ** self.q)
        return np.where(inside, self.peak_rate / g_star * g, 0.0)

    def angle(self, t: ArrayF) -> ArrayF:
        """Accumulated angle (rad): 0 before ``t0``, full swept angle after ``t1``."""
        s = self._s(t)
        sc = np.clip(s, 0.0, 1.0)
        s_star = self.p / (self.p + self.q)
        g_star = (s_star**self.p) * ((1.0 - s_star) ** self.q)
        norm = self.peak_rate / g_star * (self.t1 - self.t0) * _beta_func(self.p + 1.0, self.q + 1.0)
        return norm * _betainc(self.p + 1.0, self.q + 1.0, sc)

    def accel(self, t: ArrayF) -> ArrayF:
        """Angular acceleration contribution (rad/s^2), zero outside the window."""
        s = self._s(t)
        inside = (s >= 0.0) & (s <= 1.0)
        sc = np.clip(s, 0.0, 1.0)
        s_star = self.p / (self.p + self.q)
        g_star = (s_star**self.p) * ((1.0 - s_star) ** self.q)
        # g'(s) = s^(p-1) (1-s)^(q-1) [ p (1-s) - q s ]
        g_prime = (
            (sc ** (self.p - 1.0))
            * ((1.0 - sc) ** (self.q - 1.0))
            * (self.p * (1.0 - sc) - self.q * sc)
        )
        return np.where(inside, self.peak_rate / g_star * g_prime / (self.t1 - self.t0), 0.0)


def _bump_from_peak(
    t0: float, t1: float, peak_fraction: float, concentration: float, peak_rate: float
) -> BetaBump:
    """Build a :class:`BetaBump` whose peak sits at ``peak_fraction`` of the window.

    ``concentration`` (``= p + q``) controls the width; it is automatically
    raised if needed so that both exponents stay ``>= 3`` (required for ``C2``
    compact support) while the peak location ``peak_fraction`` is preserved.
    """
    f = float(np.clip(peak_fraction, 1.0e-3, 1.0 - 1.0e-3))
    c_min = 3.0 / min(f, 1.0 - f)
    c = max(float(concentration), c_min)
    p = c * f
    q = c * (1.0 - f)
    return BetaBump(t0=t0, t1=t1, p=p, q=q, peak_rate=peak_rate)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class SegmentGeometry:
    """Rest-pose geometry of one chain segment.

    Attributes
    ----------
    offset_world:
        Vector (m) from this segment's proximal joint to the next segment's
        proximal joint, expressed in the world frame *at address* (where every
        segment orientation is identity). Because all motion is a rotation about
        the swing-plane normal, this is also the constant body-frame offset.
    """

    offset_world: tuple[float, float, float]


@dataclass
class SwingConfig:
    """Full parameterisation of a synthetic swing.

    All angular quantities are given in degrees for readability and converted
    internally to radians. Peak *rates* are the joint-level (relative) angular
    speeds; the observable segment speed is the running sum of proximal joints.
    """

    fs_hz: float = 1000.0

    # Phase durations (seconds).
    address_s: float = 0.40
    backswing_s: float = 0.80
    downswing_s: float = 0.25  # top -> impact
    followthrough_s: float = 0.55  # impact -> finish
    finish_hold_s: float = 0.25

    # Swing-plane inclination from the horizontal ground plane (degrees).
    plane_tilt_deg: float = 55.0

    # Base (pelvis proximal joint) position in world (m); held fixed.
    base_position: tuple[float, float, float] = (0.0, 0.0, 1.05)

    # Rest geometry of the four segments (offsets in metres, world @ address).
    geometry: tuple[SegmentGeometry, SegmentGeometry, SegmentGeometry, SegmentGeometry] = field(
        default_factory=lambda: (
            SegmentGeometry(offset_world=(0.0, 0.00, 0.15)),  # pelvis -> torso base
            SegmentGeometry(offset_world=(0.0, 0.05, 0.45)),  # torso -> lead shoulder
            SegmentGeometry(offset_world=(0.0, 0.15, -0.55)),  # lead arm -> wrist
            SegmentGeometry(offset_world=(0.0, 0.20, -0.75)),  # club -> club head
        )
    )

    # Backswing: symmetric bumps (peak at mid-backswing), signed joint peak
    # rates (deg/s). Negative = "away from the ball".
    backswing_peak_rate_deg_s: tuple[float, float, float, float] = (-160.0, -240.0, -260.0, -520.0)
    backswing_concentration: float = 8.0

    # Downswing + follow-through: one skewed bump per joint over
    # [top, finish]. ``peak_fraction`` locates each joint's speed peak inside
    # that window; increasing fractions give the proximal->distal sequence.
    # Impact sits at downswing_s / (downswing_s + followthrough_s) of the window.
    downswing_peak_fraction: tuple[float, float, float, float] = (0.14, 0.20, 0.26, 0.31)
    downswing_peak_rate_deg_s: tuple[float, float, float, float] = (480.0, 460.0, 400.0, 1650.0)
    downswing_concentration: float = 10.0

    # Sensor mounting on the lead wrist / glove.
    mount_segment: int = 2  # 0=pelvis 1=torso 2=lead_arm 3=club
    # Lever arm (m) from the mount segment's proximal joint to the sensor,
    # expressed in that segment's body frame. ``None`` -> segment tip (wrist)
    # plus a small glove standoff.
    mount_lever_arm: Optional[tuple[float, float, float]] = None
    # Extrinsic quaternion [w,x,y,z] mapping sensor frame -> mount-segment frame.
    mount_extrinsic_quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    # Golfer handedness; LEFT streams are device-framed so normalize recovers RH.
    handedness: Handedness = Handedness.RIGHT

    def total_s(self) -> float:
        return (
            self.address_s
            + self.backswing_s
            + self.downswing_s
            + self.followthrough_s
            + self.finish_hold_s
        )


# ---------------------------------------------------------------------------
# Ground-truth container
# ---------------------------------------------------------------------------
@dataclass
class SwingTruth:
    """Exact ground truth for a synthetic multibody swing.

    Array shapes use ``N`` samples and ``S = 4`` segments (pelvis, torso,
    lead_arm, club in that order).
    """

    t: ArrayF  # (N,)

    # Per-segment orientation and angular kinematics.
    seg_quat: ArrayF  # (S, N, 4)  body->world, [w,x,y,z]
    seg_omega_body: ArrayF  # (S, N, 3)  rad/s, body frame
    seg_omega_world: ArrayF  # (S, N, 3)  rad/s, world frame
    seg_alpha_body: ArrayF  # (S, N, 3)  rad/s^2, body frame
    seg_alpha_world: ArrayF  # (S, N, 3)  rad/s^2, world frame
    seg_angle_rad: ArrayF  # (S, N)  cumulative plane rotation Phi_i(t)

    # Sensor (lead-wrist mount) truth.
    sensor_quat: ArrayF  # (N, 4) body->world
    sensor_pos: ArrayF  # (N, 3) m, world
    sensor_vel: ArrayF  # (N, 3) m/s, world
    sensor_acc: ArrayF  # (N, 3) m/s^2, world (linear accel, no gravity)
    gyro_body: ArrayF  # (N, 3) rad/s  measured gyro
    accel_body: ArrayF  # (N, 3) m/s^2 measured specific force

    # Club head.
    club_head_pos: ArrayF  # (N, 3) m, world
    club_head_vel: ArrayF  # (N, 3) m/s, world
    club_head_speed: ArrayF  # (N,) m/s

    # Events (exact by construction).
    address_idx: int
    top_idx: int
    impact_idx: int
    finish_idx: int

    # Kinematic-sequence diagnostics.
    x_factor_rad: ArrayF  # (N,) torso-minus-pelvis plane rotation
    seg_speed: ArrayF  # (S, N) rad/s  |omega| per segment
    seg_peak_speed_idx: ArrayF  # (S,) int  index of each segment's speed peak
    seg_peak_speed_time: ArrayF  # (S,) s
    seg_peak_speed_rad_s: ArrayF  # (S,) rad/s

    plane_normal: ArrayF  # (3,) unit swing-plane normal
    config: SwingConfig
    meta: dict[str, float] = field(default_factory=dict)

    @property
    def dt(self) -> float:
        return float(self.t[1] - self.t[0]) if self.t.shape[0] > 1 else 0.0

    def phases(self) -> SwingPhases:
        """Return the canonical :class:`SwingPhases` for pipeline integration."""
        ph = SwingPhases(
            address_idx=int(self.address_idx),
            top_idx=int(self.top_idx),
            impact_idx=int(self.impact_idx),
            finish_idx=int(self.finish_idx),
        )
        ph.validate_order()
        return ph

    def to_imu_packet(self) -> ImuPacket:
        """Package the measured sensor signals as an :class:`ImuPacket`."""
        gyro = self.gyro_body
        accel = self.accel_body
        handed = self.config.handedness
        if handed == Handedness.LEFT:
            from golfmate_algo.devices.mirror import apply_linear_map, mirror_matrix

            m = mirror_matrix(Handedness.LEFT, WristSide.LEAD)
            gyro = apply_linear_map(gyro, m)
            accel = apply_linear_map(accel, m)
        frame = SensorFrame(
            fs_hz=float(self.config.fs_hz),
            wrist=WristSide.LEAD,
            handedness=handed,
            mount_extrinsic=self.config.mount_extrinsic_quat,
            is_canonical=False,
        )
        return ImuPacket(frame=frame, t=self.t, gyro=gyro, accel=accel)

    def kinematic_sequence_ok(self) -> bool:
        """True iff downswing speed peaks occur in proximal->distal time order."""
        times = self.seg_peak_speed_time
        return bool(np.all(np.diff(times) > 0.0))


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------
def _swing_plane_normal(plane_tilt_deg: float) -> ArrayF:
    """Unit swing-plane normal, inclined ``plane_tilt_deg`` from the horizontal.

    The normal lies in the world y-z plane (perpendicular to the target line
    ``+x``) and makes ``plane_tilt_deg`` with the vertical ``+z``, so the swing
    plane makes ``plane_tilt_deg`` with the horizontal.
    """
    tilt = plane_tilt_deg * _DEG
    return np.array([0.0, np.sin(tilt), np.cos(tilt)], dtype=np.float64)


def _joint_angle_signals(
    cfg: SwingConfig, t: ArrayF
) -> tuple[ArrayF, ArrayF, ArrayF]:
    """Evaluate joint angle, rate and acceleration for all four joints.

    Returns arrays shaped ``(4, N)`` for ``theta``, ``theta_dot`` and
    ``theta_ddot`` (radians, rad/s, rad/s^2).
    """
    t_addr = cfg.address_s
    t_top = t_addr + cfg.backswing_s
    t_impact = t_top + cfg.downswing_s
    t_finish = t_impact + cfg.followthrough_s

    n_joints = 4
    theta = np.zeros((n_joints, t.shape[0]), dtype=np.float64)
    theta_dot = np.zeros_like(theta)
    theta_ddot = np.zeros_like(theta)

    for j in range(n_joints):
        bumps: list[BetaBump] = []
        # Backswing: symmetric bump over [address_end, top].
        bs_rate = cfg.backswing_peak_rate_deg_s[j] * _DEG
        if bs_rate != 0.0:
            bumps.append(
                _bump_from_peak(
                    t0=t_addr,
                    t1=t_top,
                    peak_fraction=0.5,
                    concentration=cfg.backswing_concentration,
                    peak_rate=bs_rate,
                )
            )
        # Downswing + follow-through: skewed bump over [top, finish].
        ds_rate = cfg.downswing_peak_rate_deg_s[j] * _DEG
        if ds_rate != 0.0:
            bumps.append(
                _bump_from_peak(
                    t0=t_top,
                    t1=t_finish,
                    peak_fraction=cfg.downswing_peak_fraction[j],
                    concentration=cfg.downswing_concentration,
                    peak_rate=ds_rate,
                )
            )
        for b in bumps:
            theta[j] += b.angle(t)
            theta_dot[j] += b.rate(t)
            theta_ddot[j] += b.accel(t)

    return theta, theta_dot, theta_ddot


def build_swing(config: Optional[SwingConfig] = None) -> SwingTruth:
    """Synthesise a full swing and return its exact :class:`SwingTruth`.

    Parameters
    ----------
    config:
        Swing parameterisation; defaults to a healthy, in-sequence driver.

    Returns
    -------
    SwingTruth
        Every field is analytic ground truth (see the module docstring for the
        governing equations). Use :func:`self_consistency` to verify numerically.
    """
    cfg = config if config is not None else SwingConfig()

    fs = float(cfg.fs_hz)
    dt = 1.0 / fs
    total = cfg.total_s()
    n = int(round(total * fs)) + 1
    t = np.arange(n, dtype=np.float64) * dt

    n_seg = 4
    n_axis = _swing_plane_normal(cfg.plane_tilt_deg)

    # --- driving joint signals and cumulative segment plane angles ----------
    theta, theta_dot, theta_ddot = _joint_angle_signals(cfg, t)
    phi = np.cumsum(theta, axis=0)  # (S, N) segment cumulative angle
    phi_dot = np.cumsum(theta_dot, axis=0)
    phi_ddot = np.cumsum(theta_ddot, axis=0)

    # --- per-segment orientation and angular kinematics ---------------------
    seg_quat = np.zeros((n_seg, n, 4), dtype=np.float64)
    seg_R = np.zeros((n_seg, n, 3, 3), dtype=np.float64)
    seg_omega_world = np.zeros((n_seg, n, 3), dtype=np.float64)
    seg_alpha_world = np.zeros((n_seg, n, 3), dtype=np.float64)
    seg_omega_body = np.zeros((n_seg, n, 3), dtype=np.float64)
    seg_alpha_body = np.zeros((n_seg, n, 3), dtype=np.float64)

    for s in range(n_seg):
        seg_omega_world[s] = n_axis[None, :] * phi_dot[s][:, None]
        seg_alpha_world[s] = n_axis[None, :] * phi_ddot[s][:, None]
        prev = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        for i in range(n):
            q = so3.quat_from_axis_angle(n_axis, float(phi[s, i]))
            q = so3.ensure_quat_hemisphere(q, prev)
            prev = q
            seg_quat[s, i] = q
            R = so3.quat_to_rotmat(q)
            seg_R[s, i] = R
            seg_omega_body[s, i] = R.T @ seg_omega_world[s, i]
            seg_alpha_body[s, i] = R.T @ seg_alpha_world[s, i]

    # --- serial-chain joint-origin kinematics (O_0 fixed) -------------------
    offsets_body = np.array(
        [np.asarray(g.offset_world, dtype=np.float64) for g in cfg.geometry],
        dtype=np.float64,
    )  # (S, 3)

    origin_pos = np.zeros((n_seg + 1, n, 3), dtype=np.float64)
    origin_vel = np.zeros((n_seg + 1, n, 3), dtype=np.float64)
    origin_acc = np.zeros((n_seg + 1, n, 3), dtype=np.float64)
    origin_pos[0] = np.asarray(cfg.base_position, dtype=np.float64)[None, :]

    for s in range(n_seg):
        # world offset vector of segment s at every sample: R_s @ d_s
        w = np.einsum("nij,j->ni", seg_R[s], offsets_body[s])  # (N, 3)
        om = seg_omega_world[s]
        al = seg_alpha_world[s]
        origin_pos[s + 1] = origin_pos[s] + w
        origin_vel[s + 1] = origin_vel[s] + np.cross(om, w)
        origin_acc[s + 1] = (
            origin_acc[s] + np.cross(al, w) + np.cross(om, np.cross(om, w))
        )

    # --- sensor mount kinematics -------------------------------------------
    m = int(cfg.mount_segment)
    if not 0 <= m < n_seg:
        raise ValueError("mount_segment must be in [0, 3]")
    if cfg.mount_lever_arm is None:
        # Default: segment tip (its distal joint) plus a small glove standoff.
        lever = offsets_body[m] + np.array([0.0, 0.03, 0.0], dtype=np.float64)
    else:
        lever = np.asarray(cfg.mount_lever_arm, dtype=np.float64)

    R_m = seg_R[m]  # (N, 3, 3)
    om_m = seg_omega_world[m]
    al_m = seg_alpha_world[m]
    r_world = np.einsum("nij,j->ni", R_m, lever)  # (N, 3)

    sensor_pos = origin_pos[m] + r_world
    sensor_vel = origin_vel[m] + np.cross(om_m, r_world)
    sensor_acc = (
        origin_acc[m] + np.cross(al_m, r_world) + np.cross(om_m, np.cross(om_m, r_world))
    )

    # Sensor orientation: R_sensor = R_m @ R_ext (extrinsic = sensor->segment).
    q_ext = so3.normalize_quat(cfg.mount_extrinsic_quat)
    R_ext = so3.quat_to_rotmat(q_ext)
    sensor_quat = np.zeros((n, 4), dtype=np.float64)
    gyro_body = np.zeros((n, 3), dtype=np.float64)
    accel_body = np.zeros((n, 3), dtype=np.float64)
    g_world = so3.G_WORLD
    prev = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    for i in range(n):
        R_sensor = R_m[i] @ R_ext
        q = so3.rotmat_to_quat(R_sensor)
        q = so3.ensure_quat_hemisphere(q, prev)
        prev = q
        sensor_quat[i] = q
        gyro_body[i] = R_sensor.T @ om_m[i]
        accel_body[i] = R_sensor.T @ (sensor_acc[i] - g_world)

    # --- club head ----------------------------------------------------------
    club_head_pos = origin_pos[n_seg]
    club_head_vel = origin_vel[n_seg]
    club_head_speed = np.linalg.norm(club_head_vel, axis=1)

    # --- events (exact by construction) ------------------------------------
    address_idx = max(0, int(round(cfg.address_s * fs)) - 1)
    top_idx = int(round((cfg.address_s + cfg.backswing_s) * fs))
    impact_idx = int(round((cfg.address_s + cfg.backswing_s + cfg.downswing_s) * fs))
    finish_idx = int(
        round((cfg.address_s + cfg.backswing_s + cfg.downswing_s + cfg.followthrough_s) * fs)
    )
    finish_idx = min(finish_idx, n - 1)

    # --- kinematic-sequence diagnostics ------------------------------------
    seg_speed = np.linalg.norm(seg_omega_world, axis=2)  # (S, N)
    # Restrict the peak search to the downswing/follow-through window.
    lo, hi = top_idx, finish_idx
    seg_peak_idx = np.zeros(n_seg, dtype=np.int64)
    for s in range(n_seg):
        seg_peak_idx[s] = lo + int(np.argmax(seg_speed[s, lo : hi + 1]))
    seg_peak_time = t[seg_peak_idx]
    seg_peak_speed = seg_speed[np.arange(n_seg), seg_peak_idx]

    # X-factor proxy: torso-minus-pelvis rotation about the plane normal.
    x_factor = phi[1] - phi[0]

    meta = {
        "fs_hz": fs,
        "n_samples": float(n),
        "duration_s": float(t[-1]),
        "plane_tilt_deg": float(cfg.plane_tilt_deg),
        "club_head_speed_impact_m_s": float(club_head_speed[impact_idx]),
        "club_head_speed_peak_m_s": float(np.max(club_head_speed)),
        "x_factor_top_deg": float(x_factor[top_idx] * _RAD2DEG),
    }
    for s in range(n_seg):
        meta[f"peak_speed_{SEGMENT_NAMES[s]}_deg_s"] = float(seg_peak_speed[s] * _RAD2DEG)

    return SwingTruth(
        t=t,
        seg_quat=seg_quat,
        seg_omega_body=seg_omega_body,
        seg_omega_world=seg_omega_world,
        seg_alpha_body=seg_alpha_body,
        seg_alpha_world=seg_alpha_world,
        seg_angle_rad=phi,
        sensor_quat=sensor_quat,
        sensor_pos=sensor_pos,
        sensor_vel=sensor_vel,
        sensor_acc=sensor_acc,
        gyro_body=gyro_body,
        accel_body=accel_body,
        club_head_pos=club_head_pos,
        club_head_vel=club_head_vel,
        club_head_speed=club_head_speed,
        address_idx=address_idx,
        top_idx=top_idx,
        impact_idx=impact_idx,
        finish_idx=finish_idx,
        x_factor_rad=x_factor,
        seg_speed=seg_speed,
        seg_peak_speed_idx=seg_peak_idx,
        seg_peak_speed_time=seg_peak_time,
        seg_peak_speed_rad_s=seg_peak_speed,
        plane_normal=n_axis,
        config=cfg,
        meta=meta,
    )


def casting_swing(config: Optional[SwingConfig] = None) -> SwingTruth:
    """Synthesise a pathological "casting" swing (club releases too early).

    The club's downswing speed peak is moved *ahead* of the arm's, breaking the
    proximal->distal sequence, so :meth:`SwingTruth.kinematic_sequence_ok`
    returns ``False``. Everything else remains exact ground truth.
    """
    cfg = config if config is not None else SwingConfig()
    fr = list(cfg.downswing_peak_fraction)
    # Club (distal) peaks earliest -> early cast / loss of lag.
    cfg.downswing_peak_fraction = (fr[0] + 0.02, fr[1] + 0.04, fr[2] + 0.08, 0.10)
    return build_swing(cfg)


# ---------------------------------------------------------------------------
# Self-consistency verification
# ---------------------------------------------------------------------------
def _omega_from_quats(quats: ArrayF, dt: float) -> ArrayF:
    """Numerically recover body-frame angular velocity from an orientation series.

    Uses centered finite differences of the quaternion and the identity
    ``omega_body = 2 * vec(q^{-1} (dq/dt))``.
    """
    q = np.asarray(quats, dtype=np.float64)
    dq = np.gradient(q, dt, axis=0)
    n = q.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        prod = so3.quat_multiply(so3.quat_conjugate(q[i]), dq[i])
        out[i] = 2.0 * prod[1:]
    return out


def self_consistency(truth: SwingTruth, edge_trim: int = 3) -> dict[str, float]:
    """Independently re-derive the IMU truth and report residual errors.

    The synthesised accelerometer / gyro are analytic; this routine verifies
    that they are consistent with the reported *position* trajectory and
    orientation series by numerical differentiation / re-integration. All checks
    should pass to finite-difference truncation accuracy (interior samples), so
    a few samples at each edge -- where the ``C2`` (but not ``C3``) profiles have
    corner-like third derivatives -- are trimmed before taking the max.

    Parameters
    ----------
    truth:
        The swing to verify.
    edge_trim:
        Number of samples to drop from each end before computing max residuals.

    Returns
    -------
    dict
        Residual metrics: ``accel_rms`` / ``accel_max`` (m/s^2) between the
        twice-differentiated sensor position and the accelerometer-implied world
        acceleration; ``gyro_rms`` / ``gyro_max`` (rad/s) between the
        quaternion-derived and the reported gyro; ``reintegration_max_rad`` /
        ``reintegration_final_rad`` for gyro re-integration of the sensor
        orientation; and ``velocity_rms`` (m/s) for the sensor velocity.
    """
    dt = truth.dt
    sl = slice(edge_trim, -edge_trim) if edge_trim > 0 else slice(None)

    # 1. Accelerometer <-> position: recover world accel two ways.
    a_world_meas = np.zeros_like(truth.sensor_acc)
    for i in range(truth.t.shape[0]):
        R_sensor = so3.quat_to_rotmat(truth.sensor_quat[i])
        a_world_meas[i] = R_sensor @ truth.accel_body[i] + so3.G_WORLD
    vel_num = np.gradient(truth.sensor_pos, dt, axis=0)
    acc_num = np.gradient(vel_num, dt, axis=0)
    acc_err = np.linalg.norm(acc_num - a_world_meas, axis=1)
    vel_err = np.linalg.norm(vel_num - truth.sensor_vel, axis=1)

    # 2. Gyro <-> orientation series.
    omega_num = _omega_from_quats(truth.sensor_quat, dt)
    gyro_err = np.linalg.norm(omega_num - truth.gyro_body, axis=1)

    # 3. Gyro re-integration recovers the sensor orientation.
    q = truth.sensor_quat[0].copy()
    reint_err = np.zeros(truth.t.shape[0], dtype=np.float64)
    for i in range(1, truth.t.shape[0]):
        q = so3.integrate_gyro_rk4(q, truth.gyro_body[i - 1], dt)
        reint_err[i] = so3.geodesic_distance(q, truth.sensor_quat[i])

    return {
        "accel_rms": float(np.sqrt(np.mean(acc_err**2))),
        "accel_max": float(np.max(acc_err[sl])),
        "gyro_rms": float(np.sqrt(np.mean(gyro_err**2))),
        "gyro_max": float(np.max(gyro_err[sl])),
        "velocity_rms": float(np.sqrt(np.mean(vel_err**2))),
        "velocity_max": float(np.max(vel_err[sl])),
        "reintegration_max_rad": float(np.max(reint_err)),
        "reintegration_final_rad": float(reint_err[-1]),
    }
