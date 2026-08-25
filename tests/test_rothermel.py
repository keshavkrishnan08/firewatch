"""Rothermel physical prior: sane magnitudes + vectorized-vs-scalar agreement."""
import numpy as np

from firewatch.forecast.rothermel import rothermel
from firewatch.forecast.spread import SpreadParams, precompute_ros


def test_ros_increases_with_wind():
    prev = -1
    for w in (0, 3, 6, 9, 12):
        r = rothermel(2, 0.06, w, 0.0).ros_head_ms
        assert r >= prev
        prev = r


def test_ros_magnitudes_realistic():
    # grass (FM1) with strong wind should be tens of m/min, not absurd
    r = rothermel(1, 0.06, 9.0, 0.0).ros_head_ms * 60
    assert 20 < r < 200, r
    # non-burnable is exactly zero
    assert rothermel(0, 0.06, 9.0, 0.0).ros_head_ms == 0.0


def test_slope_and_moisture_effects():
    dry = rothermel(2, 0.04, 6, 0.0).ros_head_ms
    wet = rothermel(2, 0.20, 6, 0.0).ros_head_ms
    assert dry > wet  # drier fuel spreads faster
    flat = rothermel(2, 0.06, 6, 0.0).ros_head_ms
    steep = rothermel(2, 0.06, 6, 0.5).ros_head_ms
    assert steep > flat  # upslope faster


def test_vectorized_matches_scalar(small_grid):
    """The grid-vectorized Rothermel in spread.py must match the scalar reference in a uniform patch."""
    g = small_grid
    g.fuel[:] = 2
    g.elevation[:] = 300.0  # flat -> no slope term
    g.moisture[:] = 0.06
    params = SpreadParams(wind_mult=1.0)
    ros = precompute_ros(g, params)
    r_scalar = rothermel(2, 0.06, float(np.hypot(g.wind_u[0, 0], g.wind_v[0, 0])), 0.0).ros_head_ms
    # interior cells (avoid gradient edge effects) should match the scalar head ROS closely
    assert np.allclose(ros["r_head"][5:-5, 5:-5], r_scalar, rtol=0.05, atol=1e-3)
