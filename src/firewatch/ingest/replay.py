"""Build a real EventBundle from the live public feeds (used by `make replay FIRE=<id>`).

Assembles a live common operating picture for a real, currently-active fire: locates it via NIFC
WFIGS, pulls real terrain (Terrain Tiles), wind (NWS), assets (OSM), and active-fire observations
(GOES/FIRMS), and forecasts *forward from the current observed perimeter*. Every feed degrades
gracefully; provenance records exactly which sources were live vs fallback (NFR-4, honesty).

Event config resolution order: `data/events/<id>/event.json` -> built-in registry -> treat the id as
a fire name and look it up in NIFC WFIGS.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import numpy as np

from firewatch.config import EventPaths
from firewatch.decision.exposure import cells_in_geom
from firewatch.forecast.grid import FireGrid
from firewatch.geo import destination_point, from_geojson
from firewatch.ingest import assets, cameras, dem, firms, goes, hrrr, landfire, perimeters
from firewatch.ingest.base import BBox
from firewatch.ontology.objects import (
    Fire,
    FirePerimeter,
    FireStatus,
    PerimeterSource,
    PopulationZone,
    WeatherCell,
    new_id,
)
from firewatch.ontology.store import Store
from firewatch.pipeline import EventBundle

log = logging.getLogger("firewatch.ingest")

# a small built-in registry of illustrative event configs (extend via data/events/<id>/event.json)
EVENT_REGISTRY: dict[str, dict] = {}


def _load_config(event_id: str) -> dict:
    cfg_path = EventPaths(event_id).root / "event.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text())
    if event_id in EVENT_REGISTRY:
        return EVENT_REGISTRY[event_id]
    return {"name": event_id}  # treat the id as a fire name to look up in NIFC


def build_event(event_id: str, store: Store) -> EventBundle:
    cfg = _load_config(event_id)
    name = cfg.get("name", event_id)
    half_extent_m = float(cfg.get("half_extent_m", 9000))
    cell_m = float(cfg.get("cell_m", 120))

    # 1) locate the fire + current perimeter (NIFC WFIGS)
    center = cfg.get("center")  # [lon, lat]
    if center is None:
        found = perimeters.find_fire(name)
        if found:
            center = list(found["centroid"])
            name = found["name"]
            log.info("located '%s' via NIFC at %s (%.0f acres)", name, center, found.get("acres") or 0)
    if center is None:
        raise SystemExit(
            f"could not locate fire '{name}'. Provide data/events/{event_id}/event.json with "
            f'{{"name": "...", "center": [lon, lat]}} or use `make demo` for the offline event.'
        )
    lon0, lat0 = float(center[0]), float(center[1])
    bbox = BBox.around(lon0, lat0, half_deg=half_extent_m / 111_320.0 * 1.2)
    now = datetime.now(UTC)

    perim_obs = perimeters.fetch(bbox, now - timedelta(days=5), now, fire_id="fire_" + event_id, name=name)
    current_perim = None
    if perim_obs:
        current_perim = max((from_geojson(o.geometry) for o in perim_obs), key=lambda g: g.area)

    # 2) terrain (real) + fuels + wind
    d = dem.fetch_dem(lat0, lon0, half_extent_m=half_extent_m, cell_m=cell_m, event_id=event_id)
    if d is None:
        log.warning("DEM unavailable, using flat terrain fallback")
        n = int(2 * half_extent_m / cell_m)
        from firewatch.terrain import DEM

        d = DEM(lat0, lon0, cell_m, np.full((n, n), 300.0))
    fuelinfo = landfire.fetch_fuel(d, event_id=event_id, bbox=bbox)
    wind = hrrr.fetch_wind(lat0, lon0, now, event_id=event_id)

    grid = FireGrid(
        center_lat=lat0, center_lon=lon0, cell_m=cell_m, elevation=d.elevation, fuel=fuelinfo["fuel"],
        wind_u=np.full(d.elevation.shape, wind["wind_u"]), wind_v=np.full(d.elevation.shape, wind["wind_v"]),
        moisture=np.full(d.elevation.shape, fuelinfo["moisture"]),
    )

    # 3) initial burned mask = the current observed perimeter (forecast forward from it)
    initial_mask = None
    ignition = (lon0, lat0)
    if current_perim is not None:
        initial_mask = cells_in_geom(grid, current_perim)
        if initial_mask.any():
            c = current_perim.centroid
            ignition = (float(c.x), float(c.y))
        else:
            initial_mask = None
    if initial_mask is None:  # seed a small ignition if no usable perimeter
        initial_mask = grid.ignition_mask(ignition, radius_m=cell_m)

    fire = Fire(id="fire_" + event_id, t=now, name=name, discovered_at=now, status=FireStatus.active,
                centroid={"type": "Point", "coordinates": list(ignition)},
                ignition_estimate={"type": "Point", "coordinates": list(ignition)})

    # 4) active-fire observations (best-effort)
    obs = list(perim_obs)
    obs += goes.fetch(bbox, now - timedelta(hours=6), now, fire_id=fire.id, event_id=event_id)
    obs += firms.fetch(bbox, now - timedelta(days=1), now, fire_id=fire.id, event_id=event_id)

    # 5) assets (best-effort OSM) with a fallback set of zones downwind
    zones = assets.fetch_zones(bbox, event_id=event_id)
    roads = assets.fetch_roads(bbox, event_id=event_id)
    structs = assets.fetch_buildings(bbox, event_id=event_id)
    cams = cameras.fetch(bbox, event_id=event_id)
    if not zones:
        wdir = (np.degrees(np.arctan2(wind["wind_u"], wind["wind_v"])) + 360) % 360
        from shapely.geometry import Point as _P
        zones = [PopulationZone(id=f"zone_{i}", name=f"Downwind sector {i+1} (estimated)",
                                geometry=_P(*destination_point(*ignition, wdir, dist)).buffer(0.01),
                                population=1000)
                 for i, dist in enumerate((3000, 5000, 7000))]

    weather = WeatherCell(id="wx_0", t=now, bbox=list(bbox.as_tuple()),
                          wind_u=wind["wind_u"], wind_v=wind["wind_v"],
                          rh=wind.get("rh_pct"), temp_c=wind.get("temp_c"), source=wind["source"])

    obs_perims = [FirePerimeter(id=new_id("perim"), t=o.t, fire_id=fire.id, geometry=o.geometry,
                                source=PerimeterSource.official) for o in perim_obs]

    store.put(fire)
    store.put_many(cams + zones + roads + structs + [weather] + obs_perims + obs)

    note = (f"Live COP for '{name}', forecast forward from the current NIFC perimeter. "
            f"Terrain: {'real (Terrain Tiles)' if d.elevation.std() > 1 else 'flat fallback'}; "
            f"wind: {wind['source']}; fuels: {fuelinfo['source']}. "
            f"Ablation/skill require a pre-registered retrospective with a perimeter time-series "
            f"(see docs/EVALUATION.md); this live view shows the forward forecast + decisions.")

    return EventBundle(
        event_id=event_id, store=store, grid=grid, dem=d, fire=fire, ignition_lonlat=ignition,
        ignition_time=now, zones=zones, roads=roads, structures=structs, cameras=cams,
        observations=obs, wind={"speed_ms": wind["speed_ms"], "dir_to_deg": (np.degrees(np.arctan2(wind["wind_u"], wind["wind_v"])) + 360) % 360,
                                "rh_pct": wind.get("rh_pct"), "temp_c": wind.get("temp_c"), "source": wind["source"]},
        truth_arrival=None, initial_burned_mask=initial_mask, note=note,
    )
