"""Egress-route threat timing (FR-DEC-3).

For each road segment we compute the ensemble time-to-threat (when fire is likely to reach it) and
flag routes that close *before* the zones they serve can clear — the routes an incident commander
most needs to know about. Output is `Recommendation(close_road)` objects with evidence + confidence.
"""
from __future__ import annotations

from firewatch.decision.exposure import arrival_distribution, cells_in_geom
from firewatch.forecast.engine import ForecastResult
from firewatch.ontology.objects import Recommendation, RecommendationKind, RoadSegment, new_id


def egress_threat(
    result: ForecastResult,
    roads: list[RoadSegment],
    *,
    clear_minutes: float = 60.0,
    prob_threshold: float = 0.5,
    evidence: list[str] | None = None,
) -> list[Recommendation]:
    now_min = (result.issued_at - result.ignition_time).total_seconds() / 60.0
    max_h = max(result.horizons)
    recs: list[Recommendation] = []
    for road in roads:
        mask = cells_in_geom(result.grid, road.geom())
        if not mask.any():
            continue
        dist = arrival_distribution(result.ensemble, mask)
        confidence = dist.prob_burned_by(now_min + max_h)
        if confidence < 0.1:
            continue
        tstar = dist.lead_time_minutes(prob_threshold, now_min)  # minutes until route threatened
        closes_before_clear = tstar is not None and tstar <= clear_minutes
        name = road.name or f"segment {road.id[:8]}"
        if closes_before_clear:
            rationale = (
                f"Egress route '{name}' projected to be threatened in ~{tstar:.0f} min — "
                f"before a ~{clear_minutes:.0f} min clearance window. P(threatened) = {confidence:.0%}. "
                f"Prioritize or find an alternate."
            )
            urgency = min(1.0, confidence * (1.0 + (clear_minutes - tstar) / clear_minutes))
        else:
            eta = f"~{tstar:.0f} min" if tstar is not None else f">{max_h} min"
            rationale = f"Route '{name}' threat ETA {eta}; P(threatened) = {confidence:.0%}."
            urgency = confidence * 0.4
        recs.append(
            Recommendation(
                id=new_id("rec"),
                t=result.issued_at,
                kind=RecommendationKind.close_road,
                target=road.id,
                target_name=name,
                lead_time_min=tstar,
                confidence=float(confidence),
                urgency=float(urgency),
                geometry=road.geometry,
                evidence=list(evidence or []),
                rationale=rationale,
                issued_at=result.issued_at,
            )
        )
    recs.sort(key=lambda r: r.urgency, reverse=True)
    return recs
