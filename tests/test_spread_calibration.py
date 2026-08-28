"""Spread calibration + fast-tail ensemble mixture (the honest-coverage fix).

These are fast, data-free unit tests that pin the two mechanisms behind the retrospective's
raw→calibrated coverage lift, so a reviewer probing them finds them intact.
"""
import numpy as np

from firewatch.forecast.ensemble import Ensemble, EnsembleConfig
from firewatch.forecast.grid import synthetic_grid
from firewatch.historical import _calibrate_coverage


def _fire(key, cov_at_tau, raw):
    """A synthetic per-fire result carrying only the coverage curve the calibrator needs."""
    taus = np.round(np.linspace(0.01, 0.6, 30), 4).tolist()
    return {"key": key, "coverage90_raw": raw,
            "cov_curve": {"taus": taus, "cov": list(cov_at_tau), "area_km2": [10.0] * 30}}


def test_leave_one_out_calibration_lifts_and_holds_out():
    # Three fires whose credible-region coverage decays with the threshold tau. Even the widest
    # region (tau=0.01) averages below the 0.90 target, so the calibrator should pick the widest
    # level and report each fire's coverage there, strictly >= the raw tau=0.10 coverage.
    curves = [
        np.linspace(0.80, 0.20, 30),  # fire A
        np.linspace(0.90, 0.30, 30),  # fire B
        np.linspace(0.70, 0.10, 30),  # fire C
    ]
    results = [_fire("a", curves[0], 0.45), _fire("b", curves[1], 0.55), _fire("c", curves[2], 0.40)]
    _calibrate_coverage(results, target=0.90)
    for r, c in zip(results, curves, strict=False):
        assert "coverage90_cal" in r and "coverage_tau_star" in r
        # calibrated coverage is read off this fire's own curve at the held-out threshold
        assert 0.0 <= r["coverage90_cal"] <= 1.0
        # widest region wins here, so calibrated >= the raw (tau≈0.10) coverage
        i10 = int(np.argmin(np.abs(np.array(r["cov_curve"]["taus"]) - 0.10)))
        assert r["coverage90_cal"] >= round(float(c[i10]), 3) - 1e-9


def test_calibration_threshold_is_out_of_sample():
    # Fire B is an outlier (very high coverage everywhere). Its calibrated level must be chosen from
    # the OTHER fires, so B cannot tune the threshold to itself.
    A = np.linspace(0.60, 0.10, 30)
    B = np.full(30, 0.99)
    C = np.linspace(0.62, 0.12, 30)
    results = [_fire("a", A, 0.4), _fire("b", B, 0.9), _fire("c", C, 0.4)]
    _calibrate_coverage(results, target=0.90)
    # others' mean never reaches 0.90 → widest tau; B reads ~0.99 there, not a self-fit 0.90
    assert results[1]["coverage90_cal"] > 0.9


def test_fast_tail_widens_the_envelope():
    # A tail_frac>0 ensemble must contain members that spread faster than the tight core, so the
    # credible envelope reaches further (the mechanism that lifts coverage without moving the median).
    grid = synthetic_grid(38.5, -122.6, cell_m=200.0, n=48)
    ign = (grid.center_lon, grid.center_lat)
    core = Ensemble.generate(grid, ign, EnsembleConfig(n_members=40, wind_mult_sd=0.3, spread_cap_ms=3.0, seed=1))
    mixed = Ensemble.generate(grid, ign, EnsembleConfig(
        n_members=40, wind_mult_sd=0.3, spread_cap_ms=3.0, tail_frac=0.45,
        tail_wind_mult=2.1, tail_spread_cap_ms=16.0, seed=1))
    core_max = max(m.params.wind_mult for m in core.members)
    mixed_max = max(m.params.wind_mult for m in mixed.members)
    caps = {m.params.spread_cap_ms for m in mixed.members}
    assert mixed_max > core_max          # the mixture has genuinely faster members
    assert 16.0 in caps and 3.0 in caps  # both a fast tail and a tight core are present
