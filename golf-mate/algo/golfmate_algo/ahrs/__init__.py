"""AHRS filters and initialization utilities."""

from golfmate_algo.ahrs.gated_vqf import (
    ComplementaryGatedAHRS,
    GateParams,
    GolfGatedAHRS,
    HAS_VQF,
    gravity_remove,
)
from golfmate_algo.ahrs.init import estimate_address_orientation, rest_detection
from golfmate_algo.ahrs.suite import (
    EKFOrientation,
    Complementary,
    FilterTuningSummary,
    GatedAdaptive,
    GyroOnly,
    MadgwickAHRS,
    MahonyAHRS,
    OrientationEstimator,
    TUNING_TABLE,
    forward_backward_filter_smooth,
    make_default_suite,
    quat_slerp,
    rts_smooth_orientations,
    tuning_table_as_dicts,
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
    "forward_backward_filter_smooth",
    "gravity_remove",
    "make_default_suite",
    "quat_slerp",
    "rest_detection",
    "rts_smooth_orientations",
    "tuning_table_as_dicts",
]
