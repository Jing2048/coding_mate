"""Golf Mate algorithm package (P0)."""

from golfmate_algo.devices import normalize_packet
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.types import (
    DiagnosticFinding,
    Handedness,
    ImuPacket,
    SensorFrame,
    SwingPhases,
    SwingReport,
    WristFeatures,
    WristSide,
)

__all__ = [
    "analyze_swing",
    "DiagnosticFinding",
    "Handedness",
    "ImuPacket",
    "normalize_packet",
    "SensorFrame",
    "SwingPhases",
    "SwingReport",
    "WristFeatures",
    "WristSide",
]

__version__ = "0.2.0"
