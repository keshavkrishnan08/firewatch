"""NIFC / WFIGS operational fire-perimeter connector.  [FR-ING-2]

Authoritative incident perimeters from the public WFIGS ArcGIS FeatureServer, used both as a late,
high-quality assimilation observation and as the ground truth that forecast IoU / lead-time metrics
are scored against. Keyless, GeoJSON out. Degrades gracefully if the service is unreachable.
"""
from __future__ import annotations

from datetime import UTC, datetime

from shapely.geometry import shape

from firewatch.ingest.base import BBox, http_get, log, soft
from firewatch.ontology.objects import Observation, ObservationKind, Provenance, new_id

# WFIGS Interagency Perimeters (current), public, no key
_CURRENT = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"


def _query(where: str, bbox: BBox | None = None) -> list[dict]:
    params = {"where": where, "outFields": "*", "f": "geojson", "returnGeometry": "true"}
    if bbox is not None:
        params.update({
            "geometry": ",".join(map(str, bbox.as_tuple())),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        })
    r = http_get(_CURRENT, params=params, timeout=45)
    if r is None:
        return []
    try:
        return r.json().get("features", [])
    except ValueError:
        return []


@soft
def find_fire(name: str) -> dict | None:
    """Look up a current fire by (case-insensitive) incident name; return name + bbox + centroid."""
    feats = _query(f"UPPER(poly_IncidentName) LIKE UPPER('%{name}%')")
    if not feats:
        feats = _query(f"UPPER(attr_IncidentName) LIKE UPPER('%{name}%')")
    if not feats:
        return None
    geom = shape(feats[0]["geometry"])
    props = feats[0].get("properties", {})
    c = geom.centroid
    minx, miny, maxx, maxy = geom.bounds
    return {
        "name": props.get("poly_IncidentName") or props.get("attr_IncidentName") or name,
        "centroid": (float(c.x), float(c.y)),
        "bbox": (minx, miny, maxx, maxy),
        "acres": props.get("poly_GISAcres"),
    }


@soft
def fetch(bbox: BBox, t0: datetime, t1: datetime, fire_id: str = "fire", name: str | None = None,
          event_id: str = "event") -> list[Observation]:
    where = f"UPPER(poly_IncidentName) LIKE UPPER('%{name}%')" if name else "1=1"
    feats = _query(where, bbox)
    out: list[Observation] = []
    for feat in feats:
        try:
            geom = shape(feat["geometry"])
        except Exception:
            continue
        props = feat.get("properties", {})
        ts = props.get("poly_DateCurrent") or props.get("poly_CreateDate")
        try:
            dt = datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else datetime.now(UTC)
        except (TypeError, ValueError, OSError):
            dt = datetime.now(UTC)
        out.append(Observation(
            id=new_id("obs"), t=dt, fire_id=fire_id, kind=ObservationKind.official_perimeter, geometry=geom,
            value={"acres": props.get("poly_GISAcres"), "incident": props.get("poly_IncidentName")},
            provenance=Provenance(source="NIFC WFIGS", product="Interagency Perimeters (current)",
                                  reported_uncertainty_m=120.0, retrieved_at=datetime.now(UTC)),
            reported_uncertainty_m=120.0,
        ))
    log.info("NIFC WFIGS: %d perimeter features", len(out))
    return out
