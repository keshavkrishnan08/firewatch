"""FIREWATCH forecast core (research heart): spread prior + ensemble + assimilation + calibration.

See docs/ARCHITECTURE.md §3.4 and docs/EVALUATION.md §3. The contribution is the assimilation +
calibration loop, not the physical prior.
"""
from firewatch.forecast.engine import (
    HORIZONS,
    ForecastResult,
    run_forecast,
    skill_vs_truth,
    truth_arrival,
)
from firewatch.forecast.ensemble import Ensemble, EnsembleConfig
from firewatch.forecast.grid import FireGrid, synthetic_grid
from firewatch.forecast.spread import SpreadParams, solve_arrival_times

__all__ = [
    "HORIZONS",
    "Ensemble",
    "EnsembleConfig",
    "FireGrid",
    "ForecastResult",
    "SpreadParams",
    "run_forecast",
    "skill_vs_truth",
    "solve_arrival_times",
    "synthetic_grid",
    "truth_arrival",
]
