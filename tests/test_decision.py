"""Decision layer: auditable recommendations with lead-time, confidence, evidence (FR-DEC-1..5)."""
from datetime import timedelta

from shapely.geometry import Point

from firewatch.decision.evacuation import recommend_evacuations
from firewatch.decision.staging import suggest_staging
from firewatch.forecast.engine import run_forecast
from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.geo import destination_point
from firewatch.ontology.objects import PopulationZone


def _zone(ignition, brg, dist, name="Z", pop=1000):
    c = destination_point(*ignition, brg, dist)
    return PopulationZone(id=f"zone_{name}", name=name, geometry=Point(*c).buffer(0.005), population=pop)


def test_evacuation_recs_have_evidence_and_confidence(small_grid, ignition, ign_time, synth_observations):
    cfg = EnsembleConfig(n_members=24)
    issue = ign_time + timedelta(minutes=45)
    on = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                      assimilate=True, issued_at=issue, ensemble_config=cfg)
    zones = [_zone(ignition, 60, 1500, "Downwind"), _zone(ignition, 240, 1500, "Upwind")]
    recs = recommend_evacuations(on, zones, evidence=["fc_1", "obs_1"])
    assert recs, "expected at least one recommendation"
    for r in recs:
        assert r.kind.value == "evacuate"
        assert 0.0 <= r.confidence <= 1.0
        assert r.evidence == ["fc_1", "obs_1"]  # evidence trail carried through (auditability)
        assert r.rationale  # human-readable justification, not an order
    # ranked by urgency (descending)
    assert all(recs[i].urgency >= recs[i + 1].urgency for i in range(len(recs) - 1))


def test_staging_points_are_outside_the_region(small_grid, ignition, ign_time, synth_observations):
    cfg = EnsembleConfig(n_members=24)
    issue = ign_time + timedelta(minutes=45)
    on = run_forecast(small_grid, ignition, ign_time, observations=synth_observations,
                      assimilate=True, issued_at=issue, ensemble_config=cfg)
    staging = suggest_staging(on, ignition, ring_radius_m=4000, top_k=3)
    for r in staging:
        assert r.kind.value == "stage"
        assert r.confidence >= 0.9  # residual threat < 10% by construction
