"""NASA FIRMS active-fire connector (VIIRS 375 m / MODIS 1 km).  [FR-ING-2]

Returns Observation objects (kind='viirs'|'modis') grouped by satellite pass, with provenance, for
the assimilation loop and as historical ground truth. Needs a free MAP_KEY (`.env`); without one the
connector degrades gracefully (yields nothing) and the forecast simply widens its uncertainty.
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from shapely.geometry import MultiPoint, Point

from firewatch.config import firms_map_key
from firewatch.ingest.base import BBox, http_get, log, soft
from firewatch.ontology.objects import Observation, ObservationKind, Provenance, new_id

_SOURCES = {
    "VIIRS_SNPP_NRT": (ObservationKind.viirs, 375.0),
    "VIIRS_NOAA20_NRT": (ObservationKind.viirs, 375.0),
    "MODIS_NRT": (ObservationKind.modis, 1000.0),
}
_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


@soft
def fetch(bbox: BBox, t0: datetime, t1: datetime, fire_id: str = "fire", event_id: str = "event",
          map_key: str | None = None) -> list[Observation]:
    key = map_key or firms_map_key()
    if not key:
        log.info("FIRMS: no MAP_KEY set, skipping (set FIRMS_MAP_KEY in .env). Picture degrades gracefully.")
        return []
    day_range = max(1, min(10, (t1.date() - t0.date()).days + 1))
    w, s, e, n = bbox.as_tuple()
    out: list[Observation] = []
    for source, (kind, res) in _SOURCES.items():
        url = f"{_BASE}/{key}/{source}/{w},{s},{e},{n}/{day_range}/{t0.date().isoformat()}"
        r = http_get(url, timeout=45)
        if r is None or not r.text.strip() or r.text.startswith("Invalid"):
            continue
        rows = list(csv.DictReader(io.StringIO(r.text)))
        # group by acquisition datetime (a pass)
        passes: dict[str, list] = {}
        for row in rows:
            try:
                dt = datetime.strptime(f"{row['acq_date']} {int(row['acq_time']):04d}", "%Y-%m-%d %H%M").replace(tzinfo=UTC)
            except (KeyError, ValueError):
                continue
            if not (t0 <= dt <= t1):
                continue
            passes.setdefault(dt.isoformat(), []).append((float(row["longitude"]), float(row["latitude"]), float(row.get("frp") or 0)))
        for iso, pts in passes.items():
            dt = datetime.fromisoformat(iso)
            geom = MultiPoint([Point(lon, lat) for lon, lat, _ in pts])
            out.append(Observation(
                id=new_id("obs"), t=dt, fire_id=fire_id, kind=kind, geometry=geom,
                value={"n_pixels": len(pts), "mean_frp": sum(p[2] for p in pts) / len(pts)},
                provenance=Provenance(source="NASA FIRMS", product=source, native_resolution_m=res,
                                      reported_uncertainty_m=res, retrieved_at=datetime.now(UTC)),
                reported_uncertainty_m=res,
            ))
    log.info("FIRMS: %d passes across sources", len(out))
    return out
