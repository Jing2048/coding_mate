"""Tests for multi-device normalize, handedness mirror, and adapter specs."""

from __future__ import annotations

import numpy as np

from golfmate_algo.devices.glove_spec import make_glove_packet
from golfmate_algo.devices.mirror import mirror_matrix
from golfmate_algo.devices.normalize import normalize_packet
from golfmate_algo.devices.watch_spec import make_watch_batch_packet
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.types import Handedness, SensorFrame, WristSide


def test_normalize_idempotent_on_default_right_lead():
    syn = planar_circular_swing()
    p1, info1 = normalize_packet(syn.packet)
    assert info1.applied_mirror is False
    assert p1.frame.is_canonical is True
    p2, info2 = normalize_packet(p1)
    assert info2.already_canonical is True
    assert np.allclose(p1.gyro, p2.gyro)
    assert np.allclose(p1.accel, p2.accel)


def test_left_handed_matches_right_after_normalize():
    right = planar_circular_swing(handedness=Handedness.RIGHT)
    left = planar_circular_swing(handedness=Handedness.LEFT)
    assert left.packet.frame.handedness == Handedness.LEFT
    nr, _ = normalize_packet(right.packet)
    nl, info = normalize_packet(left.packet)
    assert info.applied_mirror is True
    assert nl.frame.handedness == Handedness.RIGHT
    assert nl.frame.wrist == WristSide.LEAD
    assert np.allclose(nr.gyro, nl.gyro, atol=1e-9)
    assert np.allclose(nr.accel, nl.accel, atol=1e-9)


def test_pipeline_left_right_feature_consistency():
    right = planar_circular_swing(casting=False)
    left = planar_circular_swing(casting=False, handedness=Handedness.LEFT)
    rr = analyze_swing(right.packet, use_crop_lite=False)
    lr = analyze_swing(left.packet, use_crop_lite=False)
    assert abs(rr.features.tempo_s - lr.features.tempo_s) < 1e-6
    assert abs(rr.features.rhythm - lr.features.rhythm) < 1e-6
    assert abs(rr.features.plane_angle_deg - lr.features.plane_angle_deg) < 0.5
    assert lr.meta["frame"]["source_handedness"] == "left"
    assert lr.meta["frame"]["applied_mirror"] == 1.0


def test_extrinsic_rotation_applied():
    syn = planar_circular_swing()
    # 90° about Z: sensor → anatomy
    from golfmate_algo.math import so3

    q = so3.rotmat_to_quat(
        np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    )
    frame = SensorFrame(
        fs_hz=syn.packet.frame.fs_hz,
        handedness=Handedness.RIGHT,
        wrist=WristSide.LEAD,
        mount_extrinsic=tuple(float(x) for x in q),
        device_id="test/ext",
    )
    from golfmate_algo.types import ImuPacket

    pkt = ImuPacket(frame=frame, t=syn.packet.t, gyro=syn.packet.gyro, accel=syn.packet.accel)
    out, info = normalize_packet(pkt)
    assert info.applied_extrinsic is True
    R = so3.quat_to_rotmat(q)
    expect = (R @ syn.packet.gyro.T).T
    assert np.allclose(out.gyro, expect, atol=1e-9)


def test_watch_and_glove_factories():
    w = make_watch_batch_packet(handedness=Handedness.LEFT)
    g = make_glove_packet()
    wn, wi = normalize_packet(w, target_fs_hz=200.0)
    assert wn.frame.is_canonical
    assert wi.applied_mirror
    gn, _ = normalize_packet(g)
    assert gn.frame.device_id.startswith("glove_card")


def test_mirror_matrix_involutive():
    m = mirror_matrix(Handedness.LEFT, WristSide.LEAD)
    assert np.allclose(m @ m, np.eye(3))
