"""AHRS filters and initialization utilities."""

from golfmate_algo.ahrs.gated_vqf import (
    ComplementaryGatedAHRS,
    GateParams,
    GolfGatedAHRS,
    HAS_VQF,
    gravity_remove,
)
from golfmate_algo.ahrs.init import (
    estimate_address_orientation,
    estimate_gyro_bias,
    rest_detection,
)
from golfmate_algo.ahrs.suite import (
    TUNING_TABLE,
    Complementary,
    EKFOrientation,
    FilterTuningSummary,
    GatedAdaptive,
    GyroOnly,
    MadgwickAHRS,
    MahonyAHRS,
    OrientationEstimator,
    forward_backward_smooth,
    make_default_suite,
    quat_slerp,
)

__all__ = [
    "Complementary",
    "ComplementaryGatedAHRS",
    "EKFOrientation",
    "FilterTuningSummary",
    "GateParams",
    "GatedAdaptive",
    "GolfGatedAHRS",
    "GyroOnly",
    "HAS_VQF",
    "MadgwickAHRS",
    "MahonyAHRS",
    "OrientationEstimator",
    "TUNING_TABLE",
    "estimate_address_orientation",
    "estimate_gyro_bias",
    "forward_backward_smooth",
    "gravity_remove",
    "make_default_suite",
    "quat_slerp",
    "rest_detection",
]
