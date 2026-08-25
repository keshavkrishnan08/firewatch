"""Risk-to-population (FR-DEC-1): expected exposed structures/people over the forecast horizon.

Overlays the ensemble burn-probability field on building footprints and population zones. Output is
an expected-exposure number per zone and in aggregate, with the horizon it is evaluated at — never a
point claim, always the probability-weighted expectation.
"""
from __future__ import annotations

from dataclasses import dataclass

from firewatch.decision.exposure import arrival_distribution, cells_in_geom
from firewatch.forecast.engine import ForecastResult
from firewatch.ontology.objects import PopulationZone, Structure


@dataclass
class ZoneRisk:
    zone_id: str
    zone_name: str
    population: int
    prob_burned: dict[int, float]  # horizon -> P(any of zone burned)
    expected_people_exposed: dict[int, float]
    area_fraction_burned: dict[int, float]


def zone_risk(result: ForecastResult, zone: PopulationZone) -> ZoneRisk:
    mask = cells_in_geom(result.grid, zone.geom())
    n_cells = int(mask.sum())
    dist = arrival_distribution(result.ensemble, mask)
    prob_burned, expected, frac = {}, {}, {}
    for h in result.horizons:
        p = result.prob_fields[h]
        area_frac = float(p[mask].mean()) if n_cells > 0 else 0.0
        prob_burned[h] = dist.prob_burned_by(h)  # P(zone touched by fire) by horizon
        frac[h] = area_frac
        expected[h] = area_frac * zone.population  # expected people in burned fraction
    return ZoneRisk(zone.id, zone.name, zone.population, prob_burned, expected, frac)


def structures_exposed(result: ForecastResult, structures: list[Structure], horizon: int) -> dict:
    """Expected number of structures exposed at a horizon (prob-weighted) + a high-confidence count."""
    if not structures:
        return {"expected": 0.0, "high_conf": 0, "n_total": 0}
    grid = result.grid
    p = result.prob_fields[horizon]
    expected = 0.0
    high = 0
    for s in structures:
        c = s.geom("footprint").centroid
        i, j = grid.lonlat_to_cell(c.x, c.y)
        prob = float(p[i, j])
        expected += prob
        if prob >= 0.7:
            high += 1
    return {"expected": float(expected), "high_conf": int(high), "n_total": len(structures)}


def population_at_risk(result: ForecastResult, zones: list[PopulationZone]) -> dict:
    """Aggregate expected-exposure summary across zones, per horizon (FR-DEC-1)."""
    per_zone = [zone_risk(result, z) for z in zones]
    agg = {
        h: float(sum(zr.expected_people_exposed[h] for zr in per_zone)) for h in result.horizons
    }
    return {
        "issued_at": result.issued_at.isoformat(),
        "assimilation": result.assimilated,
        "aggregate_expected_people": agg,
        "zones": [
            {
                "zone_id": zr.zone_id,
                "name": zr.zone_name,
                "population": zr.population,
                "prob_burned": zr.prob_burned,
                "expected_people_exposed": zr.expected_people_exposed,
            }
            for zr in per_zone
        ],
    }
