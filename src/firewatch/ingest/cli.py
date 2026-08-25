"""`firewatch ingest --fire <id>` — pull live public feeds into the ontology for a real event."""
from __future__ import annotations

import logging

from firewatch.config import EventPaths
from firewatch.ontology.store import Store


def ingest_event(event_id: str, bbox=None, hours: int = 24) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from firewatch.ingest.replay import build_event

    paths = EventPaths(event_id).ensure()
    if paths.ontology_db.exists():
        paths.ontology_db.unlink()
    store = Store(paths.ontology_db)
    bundle = build_event(event_id, store)
    feeds = sorted({o.provenance.source for o in bundle.observations})
    print(f"\ningested '{event_id}' -> {store.count()} object-versions")
    print(f"  fire: {bundle.fire.name} @ {bundle.ignition_lonlat}")
    print(f"  feeds: {', '.join(feeds) or '(none live)'}")
    print(f"  zones: {len(bundle.zones)}  roads: {len(bundle.roads)}  structures: {len(bundle.structures)}  cameras: {len(bundle.cameras)}")
    print(f"  wind: {bundle.wind['source']}")
    print(f"\nnow run:  make replay FIRE={event_id}   (or: firewatch replay --fire {event_id})")
    store.close()
