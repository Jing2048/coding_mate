"""SO(3) unit and property tests."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from golfmate_algo.math import so3


def test_normalize_and_multiply_identity():
    q = so3.normalize_quat([0.2, 0.4, 0.1, 0.3])
    assert abs(np.linalg.norm(q) - 1.0) < 1e-12
    i = np.array([1.0, 0.0, 0.0, 0.0])
    assert np.allclose(so3.quat_multiply(q, i), q)
    assert np.allclose(so3.quat_multiply(i, q), q)


def test_double_cover_geodesic():
    q = so3.quat_from_axis_angle([0, 0, 1], 0.7)
    assert so3.geodesic_distance(q, -q) < 1e-10


def test_axis_angle_roundtrip_rotation():
    axis = np.array([1.0, 2.0, 3.0])
    axis = axis / np.linalg.norm(axis)
    ang = 1.234
    q = so3.quat_from_axis_angle(axis, ang)
    R = so3.quat_to_rotmat(q)
    q2 = so3.rotmat_to_quat(R)
    assert so3.geodesic_distance(q, q2) < 1e-10


def test_6d_roundtrip():
    q = so3.quat_from_axis_angle([0.3, -0.2, 0.8], 0.9)
    r6 = so3.quat_to_6d(q)
    q2 = so3.quat_from_6d(r6)
    assert so3.geodesic_distance(q, q2) < 1e-6


def test_integrate_constant_omega_matches_axis_angle():
    q0 = np.array([1.0, 0.0, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 1.5])
    dt = 0.01
    q1 = so3.integrate_gyro_rk4(q0, omega, dt)
    q_true = so3.quat_from_axis_angle(omega, np.linalg.norm(omega) * dt)
    assert so3.geodesic_distance(q1, q_true) < 1e-12


@given(
    st.floats(0.01, 3.0),
    st.floats(0.001, 0.05),
)
@settings(max_examples=40, deadline=None)
def test_hypothesis_integration_linear_in_angle(rate: float, dt: float):
    q = np.array([1.0, 0.0, 0.0, 0.0])
    omega = np.array([rate, 0.0, 0.0])
    q = so3.integrate_gyro_rk4(q, omega, dt)
    assert abs(np.linalg.norm(q) - 1.0) < 1e-10
    expected = so3.quat_from_axis_angle([1.0, 0.0, 0.0], rate * dt)
    assert so3.geodesic_distance(q, expected) < 1e-9
