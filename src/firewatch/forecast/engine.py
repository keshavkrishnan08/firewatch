"""High-level forecast engine: grid + ensemble + assimilation -> ontology Forecast objects (FR-FC-4).

`run_forecast(...)` is the one call the API/replay use. It builds an ensemble, optionally assimilates
observations (the ON arm), and emits per-horizon burn-probability fields, expected perimeters, 90%
regions, and probability bands ready for the COP map. The assimilate=False path is the OFF baseline —
the two together are the headline ablation (docs/EVALUATION.md §3.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from shapely.geometry.base import BaseGeometry

from firewatch.forecast.assimilation import ParticleFilterConfig, assimilate_sequence
from firewatch.forecast.ensemble import Ensemble, EnsembleConfig
from firewatch.forecast.grid import FireGrid
from firewatch.forecast.spread import SpreadParams, burned_mask, solve_arrival_times
from firewatch.geo import dice, iou, polygon_area_m2, to_geojson
from firewatch.ontology.objects import Forecast, new_id, utcnow

HORIZONS = [15, 30, 60, 180]  # minutes
PROB_BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]


@dataclass
class ForecastResult:
    grid: FireGrid
    ensemble: Ensemble
    issued_at: datetime
    ignition_time: datetime
    assimilated: bool
    horizons: list[int]
    prob_fields: dict[int, np.ndarray] = field(default_factory=dict)
    expected_perimeter: dict[int, BaseGeometry | None] = field(default_factory=dict)
    region_90: dict[int, BaseGeometry | None] = field(default_factory=dict)
    bands: dict[int, list[tuple[float, BaseGeometry]]] = field(default_factory=dict)

    def to_ontology(self, fire_id: str) -> list[Forecast]:
        out = []
        for h in self.horizons:
            p = self.prob_fields.get(h)
            out.append(
                Forecast(
                    id=new_id("fc"),
                    t=self.issued_at + timedelta(minutes=h),
                    fire_id=fire_id,
                    issued_at=self.issued_at,
                    horizon_min=h,
                    assimilation=self.assimilated,
                    prob_field={
                        "center_lat": self.grid.center_lat,
                        "center_lon": self.grid.center_lon,
                        "cell_m": self.grid.cell_m,
                        "shape": [self.grid.ny, self.grid.nx],
                        "max_prob": float(p.max()) if p is not None else 0.0,
                        "burning_area_m2": float((p >= 0.5).sum() * self.grid.cell_m**2)
                        if p is not None
                        else 0.0,
                        "bands": [
                            {"level": lvl, "geometry": to_geojson(g)}
                            for lvl, g in self.bands.get(h, [])
                            if g is not None
                        ],
                    },
                    expected_perimeter=to_geojson(self.expected_perimeter.get(h)),
                    region_90=to_geojson(self.region_90.get(h)),
                )
            )
        return out


def run_forecast(
    grid: FireGrid,
    ignition_lonlat: tuple[float, float],
    ignition_time: datetime,
    *,
    observations=None,
    assimilate: bool = True,
    issued_at: datetime | None = None,
    ensemble_config: EnsembleConfig | None = None,
    pf_config: ParticleFilterConfig | None = None,
    horizons: list[int] | None = None,
    initial_mask=None,
) -> ForecastResult:
    horizons = horizons or HORIZONS
    ens = Ensemble.generate(grid, ignition_lonlat, ensemble_config, initial_mask=initial_mask).run()
    did_assim = False
    if assimilate and observations:
        # only assimilate observations up to issue time (causal masking)
        cutoff = issued_at or utcnow()
        usable = [o for o in observations if o.t <= cutoff]
        if usable:
            assimilate_sequence(ens, usable, ignition_time, grid, pf_config)
            did_assim = True

    res = ForecastResult(
        grid=grid,
        ensemble=ens,
        issued_at=issued_at or utcnow(),
        ignition_time=ignition_time,
        assimilated=did_assim,
        horizons=horizons,
    )
    for h in horizons:
        p = ens.burn_probability(h)
        res.prob_fields[h] = p
        res.expected_perimeter[h] = grid.mask_to_polygon(p >= 0.5)
        res.region_90[h] = grid.mask_to_polygon(p >= 0.10)
        res.bands[h] = [(lvl, grid.mask_to_polygon(p >= lvl)) for lvl in PROB_BANDS]
        res.bands[h] = [(lvl, g) for lvl, g in res.bands[h] if g is not None]
    return res


# ── skill metrics (shared by demo + retrospective) ───────────────────────────


def truth_arrival(grid: FireGrid, ignition_lonlat, params: SpreadParams | None = None) -> np.ndarray:
    """A single deterministic 'ground-truth' spread run (used for the synthetic demo + as the
    reference in evaluation). Clearly a model run — labeled as such wherever it is reported."""
    ign = grid.ignition_mask(ignition_lonlat, radius_m=150.0)
    return solve_arrival_times(grid, ign, params or SpreadParams())


def skill_vs_truth(result: ForecastResult, truth: np.ndarray) -> dict[int, dict[str, float]]:
    """IoU / Dice / Brier / coverage of a forecast vs a truth arrival map, per horizon."""
    from firewatch.forecast.calibrate import brier_score, coverage

    out: dict[int, dict[str, float]] = {}
    grid = result.grid
    for h in result.horizons:
        p = result.prob_fields[h]
        truth_mask = burned_mask(truth, h)
        pred_poly = result.expected_perimeter[h]
        truth_poly = grid.mask_to_polygon(truth_mask)
        cov = coverage(p, truth_mask, (0.5, 0.8, 0.9))
        out[h] = {
            "iou": iou(pred_poly, truth_poly),
            "dice": dice(pred_poly, truth_poly),
            "brier": brier_score(p, truth_mask.astype(float)),
            "coverage_90": cov[0.9],
            "region90_area_km2": (polygon_area_m2(result.region_90[h]) / 1e6)
            if result.region_90[h] is not None
            else 0.0,
        }
    return out
