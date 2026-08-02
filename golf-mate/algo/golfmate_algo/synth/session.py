"""Multi-swing session generator.

A single swing lasts about two seconds, which is short enough that plain gyro
integration is hard to beat. Real usage is a range session: many swings
separated by quiet intervals, over tens of seconds to minutes. That is the
regime where gyro bias and its random walk dominate and where bounded-drift
filtering has to earn its place. Benchmarking only on isolated swings would
therefore reach the wrong conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.math import so3
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.types import ImuPacket, SensorFrame, WristSide

ArrayF = NDArray[np.float64]


def _slerp(q0: ArrayF, q1: ArrayF, t: float) -> ArrayF:
    q0 = so3.normalize_quat(q0)
    q1 = so3.normalize_quat(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1, dot = -q1, -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        return so3.normalize_quat(q0 + t * (q1 - q0))
    theta = float(np.arccos(dot))
    s = float(np.sin(theta))
    return so3.normalize_quat(
        (np.sin((1.0 - t) * theta) / s) * q0 + (np.sin(t * theta) / s) * q1
    )


@dataclass
class SwingSession:
    packet: ImuPacket
    quats_true: ArrayF
    swing_slices: list[slice]
    rest_mask_true: NDArray[np.bool_]
    n_swings: int


def make_session(
    n_swings: int = 8,
    fs_hz: float = 200.0,
    rest_between_s: float = 3.0,
    *,
    seed: int = 0,
    plane_tilt_deg: float = 55.0,
) -> SwingSession:
    """Concatenate swings separated by quiet rest intervals.

    Rest segments hold the final orientation of the preceding swing, so the
    ground-truth quaternion track stays continuous and gravity remains the only
    specific force while at rest.
    """
    rng = np.random.default_rng(seed)
    g_world = so3.G_WORLD

    gyros: list[ArrayF] = []
    accels: list[ArrayF] = []
    quats: list[ArrayF] = []
    slices: list[slice] = []
    rest_flags: list[NDArray[np.bool_]] = []
    cursor = 0

    n_rest = int(round(rest_between_s * fs_hz))

    def append_rest(q_hold: ArrayF, count: int) -> None:
        """Static hold: zero rate, specific force is gravity in the held pose."""
        nonlocal cursor
        if count <= 0:
            return
        a = -so3.quat_to_rotmat(q_hold).T @ g_world
        gyros.append(np.zeros((count, 3), dtype=np.float64))
        accels.append(np.tile(a, (count, 1)))
        quats.append(np.tile(q_hold, (count, 1)))
        rest_flags.append(np.ones(count, dtype=bool))
        cursor += count

    def append_reorient(q_from: ArrayF, q_to: ArrayF, duration_s: float) -> ArrayF:
        """Slow rotation in place between poses.

        Gyro is derived from the quaternion track so it stays consistent with
        the orientation, and the specific force is gravity alone. Rotating about
        the sensor's own centre keeps that exact, which is what makes the whole
        session self-consistent: accelerometer and orientation never disagree.
        """
        nonlocal cursor
        count = int(round(duration_s * fs_hz))
        if count < 2:
            return q_from.copy()
        ts = np.linspace(0.0, 1.0, count)
        smooth = ts * ts * (3.0 - 2.0 * ts)
        q_seq = np.zeros((count, 4), dtype=np.float64)
        prev = q_from
        for i, u in enumerate(smooth):
            q_seq[i] = so3.ensure_quat_hemisphere(_slerp(q_from, q_to, float(u)), prev)
            prev = q_seq[i]

        g_seq = np.zeros((count, 3), dtype=np.float64)
        a_seq = np.zeros((count, 3), dtype=np.float64)
        for i in range(count):
            if i == 0:
                dq = so3.quat_multiply(so3.quat_conjugate(q_seq[0]), q_seq[1])
                step = 1.0 / fs_hz
            elif i == count - 1:
                dq = so3.quat_multiply(so3.quat_conjugate(q_seq[-2]), q_seq[-1])
                step = 1.0 / fs_hz
            else:
                dq = so3.quat_multiply(so3.quat_conjugate(q_seq[i - 1]), q_seq[i + 1])
                step = 2.0 / fs_hz
            vec = dq[1:]
            nv = float(np.linalg.norm(vec))
            angle = 2.0 * float(np.arctan2(nv, abs(dq[0])))
            axis = vec / nv if nv > 1e-12 else np.zeros(3)
            if dq[0] < 0:
                axis = -axis
            g_seq[i] = axis * (angle / step)
            a_seq[i] = -so3.quat_to_rotmat(q_seq[i]).T @ g_world

        gyros.append(g_seq)
        accels.append(a_seq)
        quats.append(q_seq)
        rest_flags.append(np.zeros(count, dtype=bool))
        cursor += count
        return q_seq[-1].copy()

    swing_specs = []
    for k in range(n_swings):
        swing_specs.append(
            planar_circular_swing(
                fs_hz=fs_hz,
                backswing_s=float(rng.uniform(0.65, 0.95)),
                downswing_s=float(rng.uniform(0.20, 0.30)),
                plane_tilt_deg=plane_tilt_deg,
                casting=bool(k % 4 == 3),
            )
        )

    q_current = swing_specs[0].quats_true[0].copy()
    append_rest(q_current, n_rest)

    for k, sw in enumerate(swing_specs):
        if not np.allclose(q_current, sw.quats_true[0], atol=1e-9):
            q_current = append_reorient(q_current, sw.quats_true[0], 1.2)
            append_rest(q_current, n_rest // 2)

        n_s = sw.packet.t.shape[0]
        gyros.append(sw.packet.gyro.copy())
        accels.append(sw.packet.accel.copy())
        quats.append(sw.quats_true.copy())
        rest_flags.append(np.zeros(n_s, dtype=bool))
        slices.append(slice(cursor, cursor + n_s))
        cursor += n_s
        q_current = sw.quats_true[-1].copy()
        append_rest(q_current, n_rest)

    gyro = np.vstack(gyros)
    accel = np.vstack(accels)
    quat = np.vstack(quats)
    rest_mask = np.concatenate(rest_flags)
    n = gyro.shape[0]
    t = np.arange(n, dtype=np.float64) / fs_hz

    packet = ImuPacket(
        frame=SensorFrame(fs_hz=fs_hz, wrist=WristSide.LEAD), t=t, gyro=gyro, accel=accel
    )
    return SwingSession(
        packet=packet,
        quats_true=quat,
        swing_slices=slices,
        rest_mask_true=rest_mask,
        n_swings=n_swings,
    )
