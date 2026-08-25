"""Ontology store: versioned as-of-time reads, provenance, geometry round-trip (FR-ONT-1..3)."""
from datetime import timedelta

import pytest
from pydantic import ValidationError

from firewatch.ontology.objects import (
    Fire,
    FireStatus,
    Observation,
    ObservationKind,
    Provenance,
    new_id,
)
from firewatch.ontology.store import Store


def test_time_travel_reads_as_of(ign_time):
    store = Store()
    fid = "fire_x"
    store.put(Fire(id=fid, t=ign_time, name="X", discovered_at=ign_time, status=FireStatus.active))
    store.put(Fire(id=fid, t=ign_time + timedelta(hours=2), name="X", discovered_at=ign_time, status=FireStatus.contained))
    # as of t0 -> active; as of t0+3h -> contained; before t0 -> nothing
    assert store.get("Fire", fid, ign_time).status == FireStatus.active
    assert store.get("Fire", fid, ign_time + timedelta(hours=3)).status == FireStatus.contained
    assert store.get("Fire", fid, ign_time - timedelta(hours=1)) is None
    assert len(store.history("Fire", fid)) == 2


def test_state_at_latest_per_id(ign_time):
    store = Store()
    for k in range(3):
        store.put(Fire(id=f"f{k}", t=ign_time, name=f"f{k}", discovered_at=ign_time))
    assert len(store.state_at("Fire")) == 3


def test_provenance_mandatory():
    with pytest.raises(ValidationError):
        Observation(id=new_id("o"), fire_id="f", kind=ObservationKind.goes)  # no provenance


def test_geometry_roundtrip(ign_time):
    from shapely.geometry import MultiPoint

    store = Store()
    o = Observation(id=new_id("o"), t=ign_time, fire_id="f", kind=ObservationKind.viirs,
                    geometry=MultiPoint([(-122.6, 38.5), (-122.61, 38.51)]),
                    provenance=Provenance(source="s", product="p"))
    store.put(o)
    got = store.state_at("Observation")[0]
    assert got.geom().geom_type == "MultiPoint"
    assert got.provenance.source == "s"
