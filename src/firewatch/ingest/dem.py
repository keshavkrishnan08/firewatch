"""Digital-elevation connector — real terrain from AWS Terrain Tiles (keyless).  [FR-ING-2]

Fetches Mapzen/Terrarium PNG tiles (AWS Open Data: elevation-tiles-prod), decodes elevation, and
resamples into a local meter grid centered on the fire — the surface for both the ROS slope term and
the georeferencing ray-cast (`perception/georeference.py`). Degrades to a flat DEM if unreachable.
"""
from __future__ import annotations

import io
import math

import numpy as np

from firewatch.geo import Projector
from firewatch.ingest.base import http_get, log, soft
from firewatch.terrain import DEM

_TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def _deg2tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    lat_r = math.radians(lat)
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


def _tile2deg(x: float, y: float, z: int) -> tuple[float, float]:
    n = 2**z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


@soft
def fetch_dem(center_lat: float, center_lon: float, half_extent_m: float = 12000.0,
              cell_m: float = 90.0, zoom: int = 12, event_id: str = "event") -> DEM | None:
    """Real DEM around (center_lat, center_lon) resampled to a local meter grid."""
    from PIL import Image

    proj = Projector(center_lat, center_lon)
    n = int(2 * half_extent_m / cell_m)
    xs = (np.arange(n) - (n - 1) / 2.0) * cell_m
    ys = (np.arange(n) - (n - 1) / 2.0) * cell_m
    XX, YY = np.meshgrid(xs, ys)
    lon, lat = proj.to_wgs84(XX.ravel(), YY.ravel())
    lon = np.asarray(lon)
    lat = np.asarray(lat)

    # tile range covering the footprint
    tx = np.array([_deg2tile(lo, la, zoom)[0] for lo, la in zip(lon, lat, strict=False)])
    ty = np.array([_deg2tile(lo, la, zoom)[1] for lo, la in zip(lon, lat, strict=False)])
    x0, x1 = int(np.floor(tx.min())), int(np.floor(tx.max()))
    y0, y1 = int(np.floor(ty.min())), int(np.floor(ty.max()))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 64:
        log.warning("DEM: tile span too large (%d) — lower zoom", (x1 - x0 + 1) * (y1 - y0 + 1))
        return None

    tiles: dict[tuple[int, int], np.ndarray] = {}
    for xi in range(x0, x1 + 1):
        for yi in range(y0, y1 + 1):
            r = http_get(_TILE.format(z=zoom, x=xi, y=yi), timeout=30)
            if r is None:
                continue
            arr = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=np.float64)
            elev = arr[..., 0] * 256.0 + arr[..., 1] + arr[..., 2] / 256.0 - 32768.0
            tiles[(xi, yi)] = elev
    if not tiles:
        return None

    out = np.zeros(lon.shape)
    for k, (lo, la) in enumerate(zip(lon, lat, strict=False)):
        fx, fy = _deg2tile(lo, la, zoom)
        xi, yi = int(np.floor(fx)), int(np.floor(fy))
        tile = tiles.get((xi, yi))
        if tile is None:
            continue
        px = int((fx - xi) * tile.shape[1])
        py = int((fy - yi) * tile.shape[0])
        out[k] = tile[min(py, tile.shape[0] - 1), min(px, tile.shape[1] - 1)]
    elev = out.reshape(n, n)
    log.info("DEM: %d tiles, elevation %.0f–%.0f m", len(tiles), elev.min(), elev.max())
    return DEM(center_lat, center_lon, cell_m, elev)
