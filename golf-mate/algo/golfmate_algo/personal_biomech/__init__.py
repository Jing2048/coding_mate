"""Personal biomechanics prior, practice-loop, and strategy feature engines."""

from golfmate_algo.personal_biomech.context import SwingContext
from golfmate_algo.personal_biomech.cues import PracticeCue, cue_for_metric
from golfmate_algo.personal_biomech.practice import (
    PRACTICE_LOOP_VERSION,
    PracticeLoopFeatures,
    build_practice_loop_features,
)
from golfmate_algo.personal_biomech.prior import (
    CORE_PRIOR_METRICS,
    PERSONAL_BASELINE_VERSION,
    MetricPrior,
    MetricScore,
    PersonalBiomechPrior,
    PersonalScore,
    extract_core_metrics,
    fit_personal_prior,
    score_against_prior,
)
from golfmate_algo.personal_biomech.strategy import (
    STRATEGY_VERSION,
    StrategyFeatures,
    build_strategy_features,
)

__all__ = [
    "CORE_PRIOR_METRICS",
    "PERSONAL_BASELINE_VERSION",
    "PRACTICE_LOOP_VERSION",
    "STRATEGY_VERSION",
    "MetricPrior",
    "MetricScore",
    "PersonalBiomechPrior",
    "PersonalScore",
    "PracticeCue",
    "PracticeLoopFeatures",
    "StrategyFeatures",
    "SwingContext",
    "build_practice_loop_features",
    "build_strategy_features",
    "cue_for_metric",
    "extract_core_metrics",
    "fit_personal_prior",
    "score_against_prior",
]
