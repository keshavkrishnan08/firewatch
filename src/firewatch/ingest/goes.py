"""GOES-R ABI Fire Detection & Characterization connector.  [FR-ING-2]

Geostationary active-fire (~5-min CONUS cadence) via goes2go from AWS Open Data — the high-cadence
temporal backbone of the assimilation loop. Fire pixels (nonzero fire radiative power) are converted
from the ABI fixed grid to lon/lat via the geostationary projection and grouped per timestep into an
Observation(kind='goes'). Best-effort: on any failure the connector yields nothing (FR-ING-5).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shapely.geometry import MultiPoint, Point

from firewatch.ingest.base import BBox, log, soft
from firewatch.ontology.objects import Observation, ObservationKind, Provenance, new_id


@soft
def fetch(bbox: BBox, t0: datetime, t1: datetime, fire_id: str = "fire", event_id: str = "event",
          satellite: int = 18, max_steps: int = 6) -> list[Observation]:
    import numpy as np
    import pyproj
    from goes2go import GOES

    g = GOES(satellite=satellite, product="ABI-L2-FDCC")
    span = (t1 - t0).total_seconds()
    times = [t0 + timedelta(seconds=span * k / max(1, max_steps - 1)) for k in range(max_steps)]
    out: list[Observation] = []
    for t in times:
        try:
            ds = g.nearesttime(t.strftime("%Y-%m-%d %H:%M"))
        except Exception as e:
            log.warning("GOES nearesttime %s: %s", t, e)
            continue
        if ds is None or "Power" not in ds:
            continue
        power = np.asarray(ds["Power"].values)
        iy, ix = np.where(np.isfinite(power) & (power > 0))
        if len(iy) == 0 and "Mask" in ds:
            # Fall back to the FDC fire Mask when radiative power is unretrieved (NaN) — common for
            # smaller or view-obscured fires. Only used when Power yields nothing, so fires already
            # detected by Power are unchanged. Codes 10–15 (fire) and 30–35 (temporally filtered).
            m = np.asarray(ds["Mask"].values)
            iy, ix = np.where(np.isin(m, (10, 11, 12, 13, 14, 15, 30, 31, 32, 33, 34, 35)))
        if len(iy) == 0:
            continue
        p = ds["goes_imager_projection"]
        h = float(p.attrs["perspective_point_height"])
        proj = pyproj.Proj(proj="geos", h=h, lon_0=float(p.attrs["longitude_of_projection_origin"]),
                           sweep=str(p.attrs["sweep_angle_axis"]),
                           a=float(p.attrs["semi_major_axis"]), b=float(p.attrs["semi_minor_axis"]))
        xs = np.asarray(ds["x"].values) * h
        ys = np.asarray(ds["y"].values) * h
        lon, lat = proj(xs[ix], ys[iy], inverse=True)
        pts = [Point(float(lo), float(la)) for lo, la in zip(lon, lat, strict=False)
               if bbox.minlon <= lo <= bbox.maxlon and bbox.minlat <= la <= bbox.maxlat]
        if not pts:
            continue
        tt = t.replace(tzinfo=UTC)
        out.append(Observation(
            id=new_id("obs"), t=tt, fire_id=fire_id, kind=ObservationKind.goes,
            geometry=MultiPoint(pts), value={"n_pixels": len(pts)},
            provenance=Provenance(source=f"GOES-{satellite} ABI", product="ABI-L2-FDCC",
                                  native_resolution_m=2000.0, reported_uncertainty_m=2000.0,
                                  retrieved_at=datetime.now(UTC)),
            reported_uncertainty_m=2000.0,
        ))
    log.info("GOES: %d timesteps with fire pixels", len(out))
    return out
