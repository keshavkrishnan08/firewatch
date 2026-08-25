"""Assets connector — roads, buildings, and population zones from OpenStreetMap (FR-ING-2).

Roads (egress graph), buildings (exposure), and populated places (evacuation zones) via osmnx /
Overpass — keyless. Best-effort with graceful degradation: on failure the decision layer simply has
fewer assets to reason over (FR-ING-5).
"""
from __future__ import annotations

from shapely.geometry import Point

from firewatch.ingest.base import BBox, log, soft
from firewatch.ontology.objects import PopulationZone, RoadSegment, Structure


@soft
def fetch_roads(bbox: BBox, event_id: str = "event", max_edges: int = 400) -> list[RoadSegment]:
    import osmnx as ox

    w, s, e, n = bbox.as_tuple()
    try:
        G = ox.graph_from_bbox(bbox=(w, s, e, n), network_type="drive", simplify=True)
    except TypeError:  # older osmnx signature
        G = ox.graph_from_bbox(n, s, e, w, network_type="drive", simplify=True)
    _, edges = ox.graph_to_gdfs(G)
    roads = []
    for i, (_, row) in enumerate(edges.iterrows()):
        if i >= max_edges:
            break
        geom = row.geometry
        name = row.get("name", "")
        if isinstance(name, list):
            name = name[0] if name else ""
        if name is None or isinstance(name, float):  # pandas NaN for unnamed OSM ways
            name = ""
        roads.append(RoadSegment(id=f"road_{i}", geometry=geom, name=str(name),
                                 highway=str(row.get("highway", "road"))))
    log.info("OSM roads: %d segments", len(roads))
    return roads


@soft
def fetch_buildings(bbox: BBox, event_id: str = "event", max_buildings: int = 800) -> list[Structure]:
    import osmnx as ox

    w, s, e, n = bbox.as_tuple()
    try:
        gdf = ox.features_from_bbox(bbox=(w, s, e, n), tags={"building": True})
    except TypeError:
        gdf = ox.features_from_bbox(n, s, e, w, tags={"building": True})
    structs = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        if i >= max_buildings:
            break
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        structs.append(Structure(id=f"bldg_{i}", footprint=geom.centroid.buffer(0.00015),
                                  type=str(row.get("building", "yes")), population_est=2.6))
    log.info("OSM buildings: %d structures", len(structs))
    return structs


@soft
def fetch_zones(bbox: BBox, event_id: str = "event") -> list[PopulationZone]:
    """Populated places (villages/towns/suburbs) -> evacuation zones."""
    import osmnx as ox

    w, s, e, n = bbox.as_tuple()
    tags = {"place": ["hamlet", "village", "town", "suburb", "neighbourhood"]}
    try:
        gdf = ox.features_from_bbox(bbox=(w, s, e, n), tags=tags)
    except TypeError:
        gdf = ox.features_from_bbox(n, s, e, w, tags=tags)
    zones = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        c = geom.centroid
        try:
            pop = int(row.get("population")) if row.get("population") else 1200
        except (TypeError, ValueError):
            pop = 1200
        zones.append(PopulationZone(id=f"zone_{i}", name=str(row.get("name", f"Place {i}")),
                                    geometry=Point(c.x, c.y).buffer(0.006), population=pop))
    log.info("OSM zones: %d populated places", len(zones))
    return zones
