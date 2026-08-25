"""The thesis, as a test: assimilation ON must beat OFF, and the filter must actually discriminate."""
from datetime import timedelta

import numpy as np

from firewatch.forecast.engine import run_forecast, skill_vs_truth
from firewatch.forecast.ensemble import EnsembleConfig


def test_assimilation_beats_baseline(small_grid, ignition, ign_time, truth, synth_observations):
    cfg = EnsembleConfig(n_members=32)
    issue = ign_time + timedelta(minutes=45)
    off = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                       assimilate=False, issued_at=issue, ensemble_config=cfg)
    on = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                      assimilate=True, issued_at=issue, ensemble_config=cfg)
    so, sf = skill_vs_truth(on, truth), skill_vs_truth(off, truth)
    mean_on = np.mean([so[h]["iou"] for h in on.horizons])
    mean_off = np.mean([sf[h]["iou"] for h in off.horizons])
    assert mean_on > mean_off  # the central claim
    assert mean_on > mean_off + 0.1  # by a clear margin on this setup


def test_filter_actually_changes_the_forecast(small_grid, ignition, ign_time, synth_observations):
    """Assimilating informative observations must change the burn-probability field (ON != OFF).

    (Note: the particle filter *resamples*, which restores ESS to ~N by design, so we check that the
    forecast itself moved rather than the post-resample ESS.)
    """
    cfg = EnsembleConfig(n_members=32)
    issue = ign_time + timedelta(minutes=45)
    off = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                       assimilate=False, issued_at=issue, ensemble_config=cfg)
    on = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                      assimilate=True, issued_at=issue, ensemble_config=cfg)
    diff = sum(float(np.abs(on.prob_fields[h] - off.prob_fields[h]).sum()) for h in on.horizons)
    assert diff > 0.0, "assimilation did not change the forecast"
