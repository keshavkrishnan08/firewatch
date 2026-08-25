"""Calibration toolkit: proper scores, reliability, recalibration, coverage."""
import numpy as np

from firewatch.forecast.calibrate import (
    brier_score,
    coverage,
    fit_temperature,
    isotonic_apply,
    isotonic_fit,
    reliability_curve,
    temperature_scale,
)


def test_brier_bounds():
    assert brier_score(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 0.0
    assert brier_score(np.array([0.0, 1.0]), np.array([1.0, 0.0])) == 1.0


def test_temperature_scaling_improves_overconfident():
    rng = np.random.default_rng(0)
    y = rng.random(4000) < 0.5
    # overconfident probs: push toward 0/1
    p = np.where(y, 0.95, 0.05) + rng.normal(0, 0.02, 4000)
    p = np.clip(p, 0.001, 0.999)
    # make them systematically miscalibrated by exaggerating
    T = fit_temperature(p, y.astype(float))
    p_cal = temperature_scale(p, T)
    assert brier_score(p_cal, y.astype(float)) <= brier_score(p, y.astype(float)) + 1e-6


def test_isotonic_is_monotone():
    rng = np.random.default_rng(1)
    p = rng.random(500)
    y = (rng.random(500) < p).astype(float)
    x, g = isotonic_fit(p, y)
    assert np.all(np.diff(g) >= -1e-9)  # non-decreasing
    out = isotonic_apply(x, g, np.array([0.1, 0.5, 0.9]))
    assert out.shape == (3,)


def test_reliability_and_coverage():
    p = np.array([0.1, 0.1, 0.9, 0.9])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    rc = reliability_curve(p, y, 10)
    assert rc.counts.sum() == 4
    prob = np.array([[0.05, 0.2], [0.6, 0.95]])
    truth = np.array([[0, 0], [1, 1]], dtype=bool)
    cov = coverage(prob, truth, (0.5, 0.9))
    assert 0.0 <= cov[0.9] <= 1.0
