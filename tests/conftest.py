"""Shared pytest fixtures. Grids/ensembles are kept small so the suite runs fast."""
from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

warnings.simplefilter("ignore")


@pytest.fixture(scope="session")
def ign_time():
    return datetime(2025, 8, 20, 18, 0, tzinfo=UTC)


@pytest.fixture
def small_grid():
    from firewatch.forecast.grid import synthetic_grid

    return synthetic_grid(38.5, -122.6, cell_m=200.0, n=48, wind_speed_ms=8.0, wind_dir_to_deg=60.0)


@pytest.fixture
def ignition():
    return (-122.6, 38.5)


@pytest.fixture
def truth(small_grid, ignition):
    from firewatch.forecast.engine import truth_arrival
    from firewatch.forecast.spread import SpreadParams

    return truth_arrival(small_grid, ignition, SpreadParams(wind_mult=1.3, wind_dir_offset_deg=12, ros_mult=1.15))


@pytest.fixture
def synth_observations(small_grid, ignition, truth, ign_time):
    """VIIRS-like hotspots + a perimeter sampled from the truth fire (labeled synthetic)."""
    from shapely.geometry import MultiPoint, Point

    from firewatch.forecast.spread import burned_mask
    from firewatch.ontology.objects import Observation, ObservationKind, Provenance, new_id

    obs = []
    rng = np.random.default_rng(0)
    for mm in (20, 40):
        mask = burned_mask(truth, mm)
        ii, jj = np.nonzero(mask)
        if not len(ii):
            continue
        sel = rng.choice(len(ii), size=min(25, len(ii)), replace=False)
        pts = MultiPoint([Point(*small_grid.cell_to_lonlat(int(ii[k]), int(jj[k]))) for k in sel])
        obs.append(Observation(id=new_id("obs"), t=ign_time + timedelta(minutes=mm), fire_id="f",
                               kind=ObservationKind.viirs, geometry=pts,
                               provenance=Provenance(source="synthetic-truth", product="VIIRS"),
                               reported_uncertainty_m=375))
    return obs
