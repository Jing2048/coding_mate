"""Tests for offline endpoint SO(3) anchors and timebase helpers."""

from __future__ import annotations

import numpy as np

from golfmate_algo.ahrs.offline_smooth import smooth_endpoint_anchors
from golfmate_algo.ahrs.suite import GyroOnly
from golfmate_algo.math import so3
from golfmate_algo.signal.resample import (
    ensure_fixed_rate_packet,
    needs_fixed_rate,
    timestamp_jitter_cv,
)
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.types import ImuPacket, SensorFrame


def _tilt_err(q, a) -> float:
    R = so3.quat_to_rotmat(q)
    up_b = -R.T @ so3.G_WORLD
    up_b = up_b / (np.linalg.norm(up_b) + 1e-12)
    a_hat = a / (np.linalg.norm(a) + 1e-12)
    return float(np.degrees(np.arccos(np.clip(np.dot(up_b, a_hat), -1, 1))))


def test_endpoint_smooth_reduces_address_tilt():
    swing = planar_circular_swing()
    pkt = swing.packet
    dt = 1.0 / pkt.frame.fs_hz
    addr = swing.phases_true.address_idx
    q_bad = so3.quat_multiply(
        so3.quat_from_axis_angle([1.0, 0.0, 0.0], np.deg2rad(8.0)),
        swing.quats_true[0],
    )
    quats, _ = GyroOnly().run(pkt.gyro, pkt.accel, dt, q0=q_bad)
    sm = smooth_endpoint_anchors(
        quats,
        pkt.gyro,
        pkt.accel,
        dt,
        address_idx=addr,
        finish_idx=swing.phases_true.finish_idx,
    )
    assert sm.applied
    before = _tilt_err(quats[addr], pkt.accel[addr])
    after = _tilt_err(sm.quats[addr], pkt.accel[addr])
    assert after <= before + 1e-6
    assert after < 2.0
    assert sm.addr_tilt_corr_deg > 1.0


def test_jitter_triggers_fixed_rate():
    swing = planar_circular_swing()
    t = swing.packet.t.copy()
    rng = np.random.default_rng(0)
    t[1:] += rng.normal(0, 0.002, size=t.size - 1)
    t = np.sort(t)
    assert timestamp_jitter_cv(t) > 0.08
    assert needs_fixed_rate(t)
    pkt = ImuPacket(
        frame=SensorFrame(fs_hz=swing.packet.frame.fs_hz, is_canonical=True),
        t=t,
        gyro=swing.packet.gyro,
        accel=swing.packet.accel,
    )
    out, applied = ensure_fixed_rate_packet(pkt)
    assert applied
    dts = np.diff(out.t)
    assert float(np.std(dts) / np.median(dts)) < 0.01
