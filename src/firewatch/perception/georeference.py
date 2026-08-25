"""Camera -> map georeferencing (NOVELTY 1).  [FR-GEO-1..5]

Given a `Camera` pose (lat/lon/elev, pan/tilt/fov) and a smoke mask, we build a pinhole ray through
each mask pixel, march it against the DEM, and take the first terrain intersection as the ground
coordinate of the plume base / fire front. We propagate pose (pan/tilt) and plume-base ambiguity
into an **uncertainty region** via Monte-Carlo sampling, and emit the result as an ontology
`Observation(kind=camera_front)` that the forecast can assimilate.

Method lineage: DEM ray-tracing + EKF (Santana 2022); monoplotting (MPT 2021). The delta here is
automation (a mask, not a manual click), skyline self-calibration (`skyline.py`), an explicit
uncertainty region, and multi-camera triangulation (`triangulate.py`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiPoint, Point

from firewatch.ontology.objects import (
    Camera,
    Observation,
    ObservationKind,
    Provenance,
    new_id,
    utcnow,
)
from firewatch.terrain import DEM


@dataclass
class GeorefResult:
    front_points: list[tuple[float, float]]  # lon/lat best-estimate ground points
    region_geojson: dict | None  # uncertainty region (GeoJSON polygon)
    char_uncertainty_m: float


def ray_direction(camera: Camera, px: float, py: float) -> tuple[float, float, float]:
    """Unit ray (east, north, up) through image pixel (px, py) for a pinhole camera at this pose."""
    f = (camera.image_width / 2.0) / math.tan(math.radians(camera.fov_deg) / 2.0)
    dx = px - camera.image_width / 2.0  # right positive
    dy = py - camera.image_height / 2.0  # down positive
    h_ang = math.degrees(math.atan2(dx, f))  # right -> +azimuth
    v_ang = math.degrees(math.atan2(dy, f))  # down  -> -elevation
    az = math.radians(camera.pan_deg + h_ang)
    el = math.radians(camera.tilt_deg - v_ang)
    ce = math.cos(el)
    return (math.sin(az) * ce, math.cos(az) * ce, math.sin(el))


def intersect_ray_dem(
    cam_xy: tuple[float, float],
    cam_elev: float,
    ray: tuple[float, float, float],
    dem: DEM,
    max_range_m: float = 25000.0,
    step_m: float | None = None,
) -> tuple[float, float] | None:
    """March a ray from the camera against the DEM; return the (x, y) local meters of first hit."""
    step = step_m or max(dem.cell_m * 0.5, 10.0)
    cx, cy = cam_xy
    de, dn, du = ray
    prev_diff = cam_elev - dem.sample_local(cx, cy)  # camera should be above ground (+)
    t = step
    while t <= max_range_m:
        x = cx + de * t
        y = cy + dn * t
        ray_h = cam_elev + du * t
        diff = ray_h - dem.sample_local(x, y)
        if diff <= 0.0 and prev_diff > 0.0:
            # crossed the surface between t-step and t -> bisect
            lo, hi = t - step, t
            for _ in range(25):
                mid = 0.5 * (lo + hi)
                xm, ym = cx + de * mid, cy + dn * mid
                if (cam_elev + du * mid) - dem.sample_local(xm, ym) <= 0.0:
                    hi = mid
                else:
                    lo = mid
            xm, ym = cx + de * hi, cy + dn * hi
            return (xm, ym)
        prev_diff = diff
        t += step
    return None


def georeference_pixel(camera: Camera, px: float, py: float, dem: DEM, **kw) -> tuple[float, float] | None:
    cam_xy = dem.lonlat_to_local(camera.lon, camera.lat)
    hit = intersect_ray_dem(cam_xy, camera.elev_m, ray_direction(camera, px, py), dem, **kw)
    if hit is None:
        return None
    return dem.local_to_lonlat(*hit)


def _plume_base_pixels(mask: np.ndarray, max_cols: int = 40) -> list[tuple[float, float]]:
    """Lowest True pixel per column (the plume base ≈ the fire front in the image)."""
    h, w = mask.shape
    cols = np.where(mask.any(axis=0))[0]
    if len(cols) == 0:
        return []
    if len(cols) > max_cols:
        cols = cols[np.linspace(0, len(cols) - 1, max_cols).astype(int)]
    pts = []
    for c in cols:
        rows = np.where(mask[:, c])[0]
        pts.append((float(c), float(rows.max())))  # (px, py) with py = base row
    return pts


def georeference_front(
    camera: Camera,
    mask: np.ndarray,
    dem: DEM,
    n_samples: int = 60,
    seed: int = 3,
    max_range_m: float = 25000.0,
) -> GeorefResult:
    """Ground front + uncertainty region from a camera pose and a smoke mask (FR-GEO-1,2)."""
    base = _plume_base_pixels(mask)
    front_points: list[tuple[float, float]] = []
    for px, py in base:
        ll = georeference_pixel(camera, px, py, dem, max_range_m=max_range_m)
        if ll is not None:
            front_points.append(ll)

    # Monte-Carlo pose + base-row ambiguity -> uncertainty cloud
    rng = np.random.default_rng(seed)
    cloud: list[tuple[float, float]] = []
    rep_cols = base[:: max(1, len(base) // 6)] if base else []
    for _ in range(n_samples):
        cam = camera.model_copy()
        cam.pan_deg = camera.pan_deg + rng.normal(0, camera.pan_uncertainty_deg)
        cam.tilt_deg = camera.tilt_deg + rng.normal(0, camera.tilt_uncertainty_deg)
        for px, py in rep_cols:
            ll = georeference_pixel(cam, px, py + rng.normal(0, 4), dem, max_range_m=max_range_m)
            if ll is not None:
                cloud.append(ll)

    region_geojson = None
    char = float(camera.pose_uncertainty_m)
    if len(cloud) >= 3:
        from firewatch.geo import polygon_area_m2, to_geojson

        hull = MultiPoint([Point(lon, lat) for lon, lat in cloud]).convex_hull
        # buffer by pose uncertainty (approx degrees) to include camera position error
        buf_deg = camera.pose_uncertainty_m / 111_320.0
        region = hull.buffer(buf_deg)
        region_geojson = to_geojson(region)
        char = math.sqrt(max(polygon_area_m2(region), 1.0))
    return GeorefResult(front_points=front_points, region_geojson=region_geojson, char_uncertainty_m=char)


def georeference_to_observation(
    camera: Camera,
    mask: np.ndarray,
    dem: DEM,
    fire_id: str,
    t=None,
    **kw,
) -> Observation | None:
    """Run georeferencing and package the result as an assimilable `camera_front` Observation."""
    res = georeference_front(camera, mask, dem, **kw)
    if not res.front_points and res.region_geojson is None:
        return None
    geom = res.region_geojson
    if geom is None and len(res.front_points) >= 2:
        geom = {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in res.front_points]}
    return Observation(
        id=new_id("obs"),
        t=t or utcnow(),
        fire_id=fire_id,
        kind=ObservationKind.camera_front,
        geometry=geom,
        value={
            "camera_id": camera.id,
            "front_points": res.front_points,
            "n_points": len(res.front_points),
        },
        provenance=Provenance(
            source=camera.network,
            product="camera_georef",
            native_resolution_m=dem.cell_m,
            reported_uncertainty_m=res.char_uncertainty_m,
            detail={"camera": camera.name},
        ),
        reported_uncertainty_m=res.char_uncertainty_m,
    )
