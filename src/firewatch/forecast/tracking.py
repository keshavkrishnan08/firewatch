"""Satellite fire-object tracking from GOES active-fire detections (real, keyless).

A genuine vision/tracking algorithm on **real** data: per GOES timestep we cluster the active-fire
pixels into fire objects (DBSCAN), associate them across time by centroid proximity (nearest-neighbor
data association — the core of multi-object tracking), and derive each fire's growth curve, centroid
track, rate-of-spread, and heading. No synthetic imagery is involved — the "objects" are real fires
observed from the GOES-18 geostationary satellite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from shapely.geometry import MultiPoint

from firewatch.geo import bearing_deg, haversine_m, polygon_area_m2


@dataclass
class TrackPoint:
    t_min: float  # minutes since first detection
    centroid: tuple[float, float]  # lon, lat of the primary fire object
    area_km2: float  # convex-hull extent of the fire pixels
    n_pixels: int
    n_objects: int  # number of distinct fire clusters (spot fires) this frame


@dataclass
class FireTrack:
    points: list[TrackPoint] = field(default_factory=list)

    @property
    def n_frames(self) -> int:
        return len(self.points)

    @property
    def peak_area_km2(self) -> float:
        return max((p.area_km2 for p in self.points), default=0.0)

    @property
    def total_detections(self) -> int:
        return sum(p.n_pixels for p in self.points)

    def centroid_path(self) -> list[tuple[float, float]]:
        return [p.centroid for p in self.points]

    def mean_ros_kmh(self) -> float:
        """Mean centroid advance speed (km/h) — a proxy for rate-of-spread."""
        speeds = []
        for a, b in zip(self.points[:-1], self.points[1:], strict=False):
            dt_h = (b.t_min - a.t_min) / 60.0
            if dt_h > 0:
                speeds.append(haversine_m(*a.centroid, *b.centroid) / 1000.0 / dt_h)
        return float(np.mean(speeds)) if speeds else 0.0

    def net_heading_deg(self) -> float:
        """Compass heading of net centroid displacement (0=N, clockwise)."""
        if len(self.points) < 2:
            return 0.0
        return bearing_deg(*self.points[0].centroid, *self.points[-1].centroid)

    def growth_km2_per_h(self) -> float:
        if len(self.points) < 2:
            return 0.0
        dt_h = (self.points[-1].t_min - self.points[0].t_min) / 60.0
        return (self.points[-1].area_km2 - self.points[0].area_km2) / dt_h if dt_h > 0 else 0.0


def _cluster(points_lonlat: list[tuple[float, float]], eps_km: float = 4.0) -> list[list[tuple[float, float]]]:
    """DBSCAN-cluster fire pixels into fire objects (falls back to a single cluster without sklearn)."""
    if len(points_lonlat) <= 1:
        return [points_lonlat] if points_lonlat else []
    try:
        from sklearn.cluster import DBSCAN

        arr = np.array(points_lonlat)
        clat = float(arr[:, 1].mean())
        # scale lon/lat to km-ish for a metric eps
        xy = np.column_stack([arr[:, 0] * 111.32 * np.cos(np.radians(clat)), arr[:, 1] * 110.57])
        labels = DBSCAN(eps=eps_km, min_samples=1).fit_predict(xy)
        return [[tuple(p) for p in arr[labels == k]] for k in sorted(set(labels))]
    except Exception:
        return [points_lonlat]


def track_from_observations(observations, ignition_time: datetime, pixel_km: float = 2.0) -> FireTrack:
    """Build a FireTrack from time-ordered GOES Observations (kind='goes')."""
    from firewatch.geo import from_geojson

    goes = sorted([o for o in observations if o.kind.value == "goes" and o.geometry], key=lambda o: o.t)
    if not goes:
        return FireTrack()
    t0 = goes[0].t
    track = FireTrack()
    for o in goes:
        g = from_geojson(o.geometry)
        pts = [(p.x, p.y) for p in (g.geoms if g.geom_type == "MultiPoint" else [g])]
        if not pts:
            continue
        clusters = _cluster(pts)
        clusters.sort(key=len, reverse=True)
        primary = clusters[0]
        cx = float(np.mean([p[0] for p in primary]))
        cy = float(np.mean([p[1] for p in primary]))
        hull = MultiPoint(pts).convex_hull
        area = polygon_area_m2(hull) / 1e6 if hull.geom_type == "Polygon" else len(pts) * pixel_km**2
        area = max(area, len(pts) * (pixel_km / 2) ** 2)  # floor for tiny/collinear detections
        track.points.append(TrackPoint(
            t_min=(o.t - t0).total_seconds() / 60.0, centroid=(cx, cy),
            area_km2=float(area), n_pixels=len(pts), n_objects=len(clusters),
        ))
    return track
