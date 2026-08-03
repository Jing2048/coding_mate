"""Reference library: ideal kinematic bands + MultiSenseGolf elite gate."""

from __future__ import annotations

from golfmate_algo.reference.ideal_kinematics import (
    IdealTemplate,
    fit_ideal_template,
    load_ideal_template,
)
from golfmate_algo.reference.score import ReferenceScore, reference_finding, score_against_reference

__all__ = [
    "IdealTemplate",
    "ReferenceScore",
    "fit_ideal_template",
    "load_ideal_template",
    "reference_finding",
    "score_against_reference",
]
