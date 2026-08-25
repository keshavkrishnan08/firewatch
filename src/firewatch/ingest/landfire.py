"""Fuels connector — Rothermel fuel model per cell (FR-ING-2).

LANDFIRE (30 m fuel models / canopy) is the intended source. Because the LANDFIRE web services are
heavy to query per-pixel, this ships a transparent **elevation/slope heuristic** fallback that maps
terrain to plausible Anderson-13 fuel models, clearly labeled as estimated — so a real-fire forecast
runs today, with LANDFIRE ingestion a documented drop-in upgrade. The forecast's contribution is the
assimilation that corrects the prior, so an approximate fuel field is acceptable and honestly labeled.
"""
from __future__ import annotations

import numpy as np

from firewatch.ingest.base import log
from firewatch.terrain import DEM


def fetch_fuel(dem: DEM, event_id: str = "event", seed: int = 3) -> dict:
    """Return {'fuel': int array (dem shape), 'moisture': float, 'source': str} (heuristic)."""
    rng = np.random.default_rng(seed)
    elev = dem.elevation
    gy, gx = np.gradient(elev, dem.cell_m)
    slope = np.hypot(gx, gy)  # rise/run

    fuel = np.full(elev.shape, 2, dtype=int)  # default: timber grass & understory
    lo, hi = np.percentile(elev, [30, 75])
    fuel[elev < lo] = 1          # low elevation -> grass (FM1)
    fuel[(elev >= lo) & (elev < hi)] = 5  # mid -> brush (FM5)
    fuel[elev >= hi] = 10        # high -> timber litter & understory (FM10)
    fuel[slope > 0.6] = 4        # steep chaparral (FM4, fast)
    # scattered non-burnable (water/rock/urban proxy) at the very lowest cells
    verylow = elev < np.percentile(elev, 3)
    fuel[verylow & (rng.random(elev.shape) < 0.5)] = 0

    log.info("fuels: heuristic fuel field (LANDFIRE ingest pending) — models present: %s",
             sorted(set(np.unique(fuel).tolist())))
    return {"fuel": fuel, "moisture": 0.07, "source": "estimated (elevation/slope heuristic; LANDFIRE pending)"}
