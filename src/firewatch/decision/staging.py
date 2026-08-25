"""Resource-staging suggestions (FR-DEC-4).

Candidate staging points that stay outside the 90% credible burn region for the forecast horizon
while minimizing response distance to the fire. Emits `Recommendation(stage)` objects; a human
selects among them.
"""
from __future__ import annotations

from shapely.geometry import Point

from firewatch.decision.exposure import arrival_distribution, cells_in_geom
from firewatch.forecast.engine import ForecastResult
from firewatch.geo import destination_point, haversine_m
from firewatch.ontology.objects import Recommendation, RecommendationKind, new_id


def suggest_staging(
    result: ForecastResult,
    fire_centroid: tuple[float, float],
    *,
    horizon: int | None = None,
    n_candidates: int = 24,
    ring_radius_m: float = 6000.0,
    safe_prob: float = 0.1,
    top_k: int = 4,
    evidence: list[str] | None = None,
) -> list[Recommendation]:
    """Ring of candidate points around the fire; keep those outside the 90% region, rank by closeness."""
    horizon = horizon or max(result.horizons)
    grid = result.grid
    p = result.prob_fields[horizon]
    lon0, lat0 = fire_centroid
    now_min = (result.issued_at - result.ignition_time).total_seconds() / 60.0

    scored: list[tuple[float, Recommendation]] = []
    for k in range(n_candidates):
        bearing = 360.0 * k / n_candidates
        lon, lat = destination_point(lon0, lat0, bearing, ring_radius_m)
        i, j = grid.lonlat_to_cell(lon, lat)
        prob_here = float(p[i, j])
        if prob_here > safe_prob:
            continue  # inside the credible burn envelope — not safe to stage
        # ensure it stays safe: arrival distribution into a small disk around the point
        disk = Point(lon, lat).buffer(300.0 / 111_320.0)
        mask = cells_in_geom(grid, disk)
        threat = arrival_distribution(result.ensemble, mask).prob_burned_by(now_min + horizon) if mask.any() else 0.0
        if threat > safe_prob:
            continue
        dist_km = haversine_m(lon, lat, lon0, lat0) / 1000.0
        # prefer closer (faster response) and lower residual threat
        score = 1.0 / (1.0 + dist_km) * (1.0 - threat)
        rec = Recommendation(
            id=new_id("rec"),
            t=result.issued_at,
            kind=RecommendationKind.stage,
            target=f"stage_{k}",
            target_name=f"Staging candidate {bearing:.0f}°",
            confidence=float(1.0 - threat),
            urgency=float(score),
            geometry={"type": "Point", "coordinates": [lon, lat]},
            evidence=list(evidence or []),
            rationale=(
                f"~{dist_km:.1f} km {_compass(bearing)} of the fire; stays outside the 90% region "
                f"through +{horizon} min (residual threat {threat:.0%}). Minimizes response distance among safe options."
            ),
            issued_at=result.issued_at,
        )
        scored.append((score, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def _compass(bearing: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int(((bearing + 22.5) % 360) // 45)]
