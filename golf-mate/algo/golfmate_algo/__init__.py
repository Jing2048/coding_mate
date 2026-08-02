"""Golf Mate algorithm package (P0)."""

from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.types import (
    DiagnosticFinding,
    ImuPacket,
    SensorFrame,
    SwingPhases,
    SwingReport,
    WristFeatures,
)

__all__ = [
    "analyze_swing",
    "DiagnosticFinding",
    "ImuPacket",
    "SensorFrame",
    "SwingPhases",
    "SwingReport",
    "WristFeatures",
]

__version__ = "0.1.0"
