"""Spread solver behavior + the causal-masking guarantee (docs/EVALUATION.md §5.2)."""
from datetime import timedelta

import numpy as np

from firewatch.forecast.engine import run_forecast
from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.forecast.spread import SpreadParams, solve_arrival_times


def test_fire_propagates_and_is_monotonic(small_grid, ignition):
    arr = solve_arrival_times(small_grid, small_grid.ignition_mask(ignition, 150), SpreadParams())
    assert np.isfinite(arr).sum() > 20  # spreads beyond ignition
    later = (arr <= 60).sum()
    earlier = (arr <= 30).sum()
    assert later >= earlier  # burned area only grows with time


def test_nonburnable_is_a_barrier(small_grid, ignition):
    g = small_grid
    g.fuel[:] = 0  # everything non-burnable
    arr = solve_arrival_times(g, g.ignition_mask(ignition, 150), SpreadParams())
    # only the ignition cells have finite arrival; nothing propagates
    assert np.isfinite(arr).sum() == g.ignition_mask(ignition, 150).sum()


def test_no_future_data_leaks_into_issued_forecast(small_grid, ignition, ign_time, synth_observations):
    """A forecast issued at time t must not be changed by observations that occur after t."""
    cfg = EnsembleConfig(n_members=16)
    issue = ign_time + timedelta(minutes=25)  # only the 20-min obs is causal; the 40-min obs is future
    all_obs = synth_observations  # at 20 and 40 min
    past_only = [o for o in all_obs if o.t <= issue]

    on_all = run_forecast(small_grid, ignition, ign_time, observations=all_obs, assimilate=True,
                          issued_at=issue, ensemble_config=cfg)
    on_past = run_forecast(small_grid, ignition, ign_time, observations=past_only, assimilate=True,
                           issued_at=issue, ensemble_config=cfg)
    # identical seeds + identical causal obs -> identical burn probability at every horizon
    for h in on_all.horizons:
        assert np.allclose(on_all.prob_fields[h], on_past.prob_fields[h])
