"""Tower-camera connector (ALERTCalifornia / ALERTWildfire).  [FR-ING-2]

Camera metadata (lat/lon/elev, pan/tilt/fov) feeds georeferencing. The ALERTCalifornia network's
imagery is publicly viewable but its metadata API is access-gated, so this connector is best-effort:
if a `data/events/<id>/cameras.json` file is present it is loaded (network operators can drop pose
metadata there); otherwise it yields nothing and the picture proceeds on satellite + perimeter feeds.
"""
from __future__ import annotations

import json

from firewatch.ingest.base import BBox, cache_dir, log, soft
from firewatch.ontology.objects import Camera, new_id


@soft
def fetch(bbox: BBox, event_id: str = "event") -> list[Camera]:
    path = cache_dir(event_id).parent / "cameras.json"
    if not path.exists():
        log.info("cameras: no local cameras.json for '%s', skipping (satellite+perimeter still drive the picture)", event_id)
        return []
    records = json.loads(path.read_text())
    cams = []
    for r in records:
        if not (bbox.minlon <= r["lon"] <= bbox.maxlon and bbox.minlat <= r["lat"] <= bbox.maxlat):
            continue
        cams.append(Camera(
            id=r.get("id", new_id("cam")), name=r.get("name", "camera"), lat=r["lat"], lon=r["lon"],
            elev_m=r.get("elev_m", 0.0), pan_deg=r.get("pan_deg", 0.0), tilt_deg=r.get("tilt_deg", 0.0),
            fov_deg=r.get("fov_deg", 60.0), network=r.get("network", "ALERTCalifornia"),
        ))
    log.info("cameras: %d loaded from cameras.json", len(cams))
    return cams
