"""Evacuation lead-time recommendations (FR-DEC-2).

For each PopulationZone we compute the ensemble arrival-time distribution into the zone, and from it:
the time until burn-probability crosses a threshold (the lead-time), a confidence band from the
ensemble spread, and an urgency score to rank zones. Every output is a `Recommendation` carrying
lead_time, confidence, and `evidence[]` (the Forecast + Observations that justify it). Human-in-the-
loop only — nothing here is phrased as an autonomous order (FR-DEC-5 / CLAUDE.md guardrail).
"""
from __future__ import annotations

from firewatch.decision.exposure import arrival_distribution, cells_in_geom
from firewatch.forecast.engine import ForecastResult
from firewatch.ontology.objects import (
    PopulationZone,
    Recommendation,
    RecommendationKind,
    new_id,
)


def recommend_evacuations(
    result: ForecastResult,
    zones: list[PopulationZone],
    *,
    threshold: float = 0.5,
    evac_clear_minutes: float = 60.0,
    evidence: list[str] | None = None,
) -> list[Recommendation]:
    """Rank zones by evacuation urgency with lead-time + confidence (FR-DEC-2)."""
    now_min = (result.issued_at - result.ignition_time).total_seconds() / 60.0
    max_h = max(result.horizons)
    recs: list[Recommendation] = []

    for zone in zones:
        mask = cells_in_geom(result.grid, zone.geom())
        if not mask.any():
            continue
        dist = arrival_distribution(result.ensemble, mask)
        confidence = dist.prob_burned_by(now_min + max_h)  # P(threatened within forecast window)
        if confidence < 0.05:
            continue  # not meaningfully threatened
        lead = dist.lead_time_minutes(threshold, now_min)
        lo = dist.quantile_minutes(0.1)
        hi = dist.quantile_minutes(0.9)
        lead_low = (lo - now_min) if lo is not None else None
        lead_high = (hi - now_min) if hi is not None else None

        # urgency: high when lead-time is short relative to the time needed to clear the zone,
        # scaled by confidence and population.
        if lead is None:
            urgency = confidence * 0.3
        else:
            slack = lead - evac_clear_minutes
            urgency = confidence * (1.0 / (1.0 + max(slack, 0.0) / 30.0))
            if slack < 0:
                urgency = min(1.0, urgency + 0.4)  # cannot clear in time -> escalate
        urgency *= 0.5 + 0.5 * min(zone.population / 2000.0, 1.0)

        if lead is not None and lead <= evac_clear_minutes:
            rationale = (
                f"Fire projected to reach {zone.name} in ~{lead:.0f} min "
                f"(80% band {lead_low:.0f}–{lead_high:.0f} min); zone needs ~{evac_clear_minutes:.0f} min to clear. "
                f"P(threatened within +{max_h} min) = {confidence:.0%}."
            )
        else:
            eta = f"~{lead:.0f} min" if lead is not None else f">{max_h} min"
            rationale = (
                f"Monitor {zone.name}: projected threat in {eta}; "
                f"P(threatened within +{max_h} min) = {confidence:.0%}."
            )

        recs.append(
            Recommendation(
                id=new_id("rec"),
                t=result.issued_at,
                kind=RecommendationKind.evacuate,
                target=zone.id,
                target_name=zone.name,
                lead_time_min=lead,
                lead_time_low_min=lead_low,
                lead_time_high_min=lead_high,
                confidence=float(confidence),
                urgency=float(min(urgency, 1.0)),
                geometry=zone.geometry,
                evidence=list(evidence or []),
                rationale=rationale,
                issued_at=result.issued_at,
            )
        )
    recs.sort(key=lambda r: r.urgency, reverse=True)
    return recs
