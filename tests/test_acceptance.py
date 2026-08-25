"""M1–M5 acceptance test (mirrors docs/ROADMAP.md) — the full stack on a small synthetic event."""
import numpy as np
import pytest

from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.ontology.store import Store
from firewatch.pipeline import run_pipeline


@pytest.fixture(scope="module")
def demo_run():
    from datetime import timedelta

    from firewatch.demo import build_demo_event

    store = Store()
    bundle = build_demo_event(store, event_id="test_demo", n=48, cell_m=200.0)
    issue = bundle.ignition_time + timedelta(minutes=90)
    result = run_pipeline(bundle, issue, ensemble_config=EnsembleConfig(n_members=24), write_outputs=False)
    return bundle, result, store


def test_m1_feeds_land_as_ontology_objects_with_provenance(demo_run):
    bundle, _, store = demo_run
    kinds = store.kinds()
    assert len(kinds) >= 6, kinds  # Fire, Camera, Zone, Road, Structure, Weather, Observation, Perimeter...
    obs = store.state_at("Observation")
    assert obs, "no observations ingested"
    assert all(o.provenance and o.provenance.source for o in obs)  # provenance mandatory (FR-ING-3)
    # multiple distinct observation modalities fused (satellite + perimeter + camera)
    assert len({o.kind.value for o in obs}) >= 3


def test_m1_replay_is_reconstructable_offline(demo_run):
    bundle, _, store = demo_run
    # the ontology store reconstructs state as-of any past instant (scrubber / offline replay)
    early = store.state_at("Observation", bundle.ignition_time)
    late = store.state_at("Observation", bundle.ignition_time.replace(year=2030))
    assert len(late) >= len(early)


def test_m3_camera_front_observation_emitted(demo_run):
    bundle, _, _ = demo_run
    cam_fronts = [o for o in bundle.observations if o.kind.value == "camera_front"]
    assert cam_fronts, "expected a georeferenced camera_front observation from the perception pipeline"
    assert cam_fronts[0].geometry is not None


def test_m4_forecast_objects_and_ablation(demo_run):
    _, result, store = demo_run
    fcs = store.state_at("Forecast")
    assert fcs, "no forecast objects written"
    assert any(f.region_90 is not None for f in fcs)  # 90% region emitted (FR-FC-4)
    so, sf = result["skill_on"], result["skill_off"]
    mean_on = np.mean([so[h]["iou"] for h in result["forecast_on"].horizons])
    mean_off = np.mean([sf[h]["iou"] for h in result["forecast_off"].horizons])
    assert mean_on > mean_off  # the thesis (FR-FC-6)


def test_m5_decisions_are_auditable(demo_run):
    _, result, _ = demo_run
    assert result["evacuations"], "no evacuation recommendations produced"
    for r in result["evacuations"]:
        assert r.evidence, "recommendation missing its evidence trail (FR-DEC-5)"
        assert 0.0 <= r.confidence <= 1.0


def test_graceful_degradation_of_a_connector():
    """A connector that raises must yield nothing, not crash the cycle (FR-ING-5)."""
    from firewatch.ingest.base import soft

    @soft
    def broken():
        raise RuntimeError("feed down")

    assert broken() == []
