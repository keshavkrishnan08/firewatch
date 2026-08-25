"""FIREWATCH decision layer (FR-DEC-1..5).

Turns the calibrated forecast into auditable, human-in-the-loop recommendations: risk-to-population,
evacuation lead-time, egress-route threat, and staging. Every Recommendation carries lead-time,
confidence, and an evidence trail; nothing is an autonomous order. See docs/PRD.md §5.6.
"""
from firewatch.decision.evacuation import recommend_evacuations
from firewatch.decision.exposure import ArrivalDistribution, arrival_distribution, cells_in_geom
from firewatch.decision.risk import population_at_risk, structures_exposed, zone_risk
from firewatch.decision.routing import egress_threat
from firewatch.decision.staging import suggest_staging

__all__ = [
    "ArrivalDistribution",
    "arrival_distribution",
    "cells_in_geom",
    "egress_threat",
    "population_at_risk",
    "recommend_evacuations",
    "structures_exposed",
    "suggest_staging",
    "zone_risk",
]
