"""Geometry & projection helpers shared across FIREWATCH.

Storage convention (see CLAUDE.md): all geometry is stored as GeoJSON-style mappings in
EPSG:4326 (lon, lat order). Metric math is done in a *local* azimuthal-equidistant projection
centered on the fire, so distances/areas are in meters over the small single-fire domain.

This module is deliberately dependency-light (numpy + pyproj + shapely) so the forecast,
georeferencing, and decision cores run without the heavy geo extras.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from shapely import geometry as sgeom
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

WGS84 = "EPSG:4326"
EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (meters)


def local_aeqd_proj4(lat0: float, lon0: float) -> str:
    """Proj4 string for an azimuthal-equidistant CRS centered on (lat0, lon0), units = meters."""
    return f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"


@dataclass
class Projector:
    """Bidirectional transform between WGS84 (lon/lat) and a local meters frame at (lat0, lon0).

    The local frame is azimuthal-equidistant centered on the origin: x east, y north, in meters.
    Accurate to well under a percent over a single-fire domain (tens of km), which is all we need.
    """

    lat0: float
    lon0: float

    def __post_init__(self) -> None:
        proj = local_aeqd_proj4(self.lat0, self.lon0)
        self._fwd = Transformer.from_crs(WGS84, proj, always_xy=True)
        self._inv = Transformer.from_crs(proj, WGS84, always_xy=True)

    def to_local(self, lon, lat):
        """(lon, lat) degrees -> (x, y) meters. Accepts scalars or numpy arrays."""
        return self._fwd.transform(lon, lat)

    def to_wgs84(self, x, y):
        """(x, y) meters -> (lon, lat) degrees. Accepts scalars or numpy arrays."""
        return self._inv.transform(x, y)

    def geom_to_local(self, geom: BaseGeometry) -> BaseGeometry:
        return shapely_transform(lambda xs, ys, z=None: self._fwd.transform(xs, ys), geom)

    def geom_to_wgs84(self, geom: BaseGeometry) -> BaseGeometry:
        return shapely_transform(lambda xs, ys, z=None: self._inv.transform(xs, ys), geom)


def to_geojson(geom: BaseGeometry | None) -> dict | None:
    """shapely geometry -> GeoJSON mapping (or None)."""
    if geom is None or geom.is_empty:
        return None
    return sgeom.mapping(geom)


def from_geojson(obj: dict | BaseGeometry | None) -> BaseGeometry | None:
    """GeoJSON mapping (or shapely geometry) -> shapely geometry (or None)."""
    if obj is None:
        return None
    if isinstance(obj, BaseGeometry):
        return obj
    return sgeom.shape(obj)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial compass bearing (degrees, 0=N, clockwise) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination_point(lon: float, lat: float, bearing: float, dist_m: float) -> tuple[float, float]:
    """Point reached from (lon, lat) going `bearing` degrees for `dist_m` meters. Returns (lon, lat)."""
    ang = dist_m / EARTH_RADIUS_M
    br = math.radians(bearing)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(ang) + math.cos(p1) * math.sin(ang) * math.cos(br))
    l2 = l1 + math.atan2(
        math.sin(br) * math.sin(ang) * math.cos(p1),
        math.cos(ang) - math.sin(p1) * math.sin(p2),
    )
    return (math.degrees(l2), math.degrees(p2))


def bbox_of(geom: BaseGeometry) -> tuple[float, float, float, float]:
    """(minlon, minlat, maxlon, maxlat) of a geometry."""
    return tuple(geom.bounds)  # type: ignore[return-value]


def buffer_bbox_deg(
    bbox: tuple[float, float, float, float], pad_m: float
) -> tuple[float, float, float, float]:
    """Pad a lon/lat bbox by approximately `pad_m` meters on every side."""
    minlon, minlat, maxlon, maxlat = bbox
    clat = (minlat + maxlat) / 2.0
    dlat = pad_m / 111_320.0
    dlon = pad_m / (111_320.0 * max(0.05, math.cos(math.radians(clat))))
    return (minlon - dlon, minlat - dlat, maxlon + dlon, maxlat + dlat)


def polygon_area_m2(geom: BaseGeometry, lat0: float | None = None, lon0: float | None = None) -> float:
    """Area of a lon/lat polygon in square meters via a local equal-distance projection."""
    if geom is None or geom.is_empty:
        return 0.0
    c = geom.centroid
    proj = Projector(lat0 if lat0 is not None else c.y, lon0 if lon0 is not None else c.x)
    return abs(proj.geom_to_local(geom).area)


def iou(a: BaseGeometry | None, b: BaseGeometry | None) -> float:
    """Intersection-over-union of two polygons (0..1). 0 if either is missing/empty."""
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    union = a.union(b).area
    return float(inter / union) if union > 0 else 0.0


def dice(a: BaseGeometry | None, b: BaseGeometry | None) -> float:
    """Sørensen-Dice coefficient of two polygons (0..1)."""
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    denom = a.area + b.area
    return float(2 * inter / denom) if denom > 0 else 0.0


def grid_axes(
    center_lat: float, center_lon: float, half_extent_m: float, cell_m: float
) -> tuple[np.ndarray, np.ndarray, Projector]:
    """Build a square, meter-spaced local grid centered on (lat, lon).

    Returns (xs, ys, projector) where xs, ys are 1-D meter coordinates (increasing east/north).
    """
    n = int(round(2 * half_extent_m / cell_m))
    coords = (np.arange(n) - (n - 1) / 2.0) * cell_m
    return coords.copy(), coords.copy(), Projector(center_lat, center_lon)
