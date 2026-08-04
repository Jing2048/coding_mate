"""On-device export contracts (Core ML path reserved / optional on macOS)."""

from __future__ import annotations

from golfmate_algo.export.edge_trajectory_contract import (
    CONTRACT_VERSION as EDGE_TRAJECTORY_CONTRACT_VERSION,
    INPUT_FS_HZ as EDGE_INPUT_FS_HZ,
    OUTPUT_DIM as EDGE_OUTPUT_DIM,
    TRAJECTORY_POINTS,
    EdgeTrajectoryOutput,
    load_edge_trajectory_schema,
    sample_trajectory_xyz,
)
from golfmate_algo.export.edge_trajectory_model import (
    EdgeTrajectoryStudent,
    extract_edge_features,
    fit_edge_student,
    load_edge_student,
    teacher_edge_output,
    train_default_edge_student,
)
from golfmate_algo.export.feature_contract import (
    CONTRACT_VERSION,
    FEATURE_NAMES,
    SwingFeatureVector,
    export_feature_vector,
    load_schema,
)

__all__ = [
    "CONTRACT_VERSION",
    "EDGE_INPUT_FS_HZ",
    "EDGE_OUTPUT_DIM",
    "EDGE_TRAJECTORY_CONTRACT_VERSION",
    "FEATURE_NAMES",
    "EdgeTrajectoryOutput",
    "EdgeTrajectoryStudent",
    "SwingFeatureVector",
    "TRAJECTORY_POINTS",
    "export_feature_vector",
    "extract_edge_features",
    "fit_edge_student",
    "load_edge_student",
    "load_edge_trajectory_schema",
    "load_schema",
    "sample_trajectory_xyz",
    "teacher_edge_output",
    "train_default_edge_student",
]
