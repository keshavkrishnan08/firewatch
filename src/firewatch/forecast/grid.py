"""The fire model grid: terrain / fuel / wind rasters in a local meter frame.

A `FireGrid` is the substrate the spread solver runs on. It can be built from ontology layer
objects (real ingest) or synthesized for the offline demo. Geometry conversions go through a
local azimuthal-equidistant `Projector` (firewatch.geo) so distances/areas are true meters.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from firewatch.geo import Projector


@dataclass
class FireGrid:
    center_lat: float
    center_lon: float
    cell_m: float
    elevation: np.ndarray  # (ny, nx) meters
    fuel: np.ndarray  # (ny, nx) int fuel-model codes
    wind_u: np.ndarray  # (ny, nx) m/s eastward @10m
    wind_v: np.ndarray  # (ny, nx) m/s northward @10m
    moisture: np.ndarray  # (ny, nx) dead fuel moisture fraction
    projector: Projector = field(init=False)

    def __post_init__(self) -> None:
        self.ny, self.nx = self.elevation.shape
        self.projector = Projector(self.center_lat, self.center_lon)
        # local meter coordinates of cell centers, centered on origin
        self._xs = (np.arange(self.nx) - (self.nx - 1) / 2.0) * self.cell_m
        self._ys = (np.arange(self.ny) - (self.ny - 1) / 2.0) * self.cell_m

    # ── coordinate transforms ───────────────────────────────────────────────────

    def cell_to_local(self, i: int, j: int) -> tuple[float, float]:
        """(row i, col j) -> (x, y) meters."""
        return float(self._xs[j]), float(self._ys[i])

    def cell_to_lonlat(self, i: int, j: int) -> tuple[float, float]:
        x, y = self.cell_to_local(i, j)
        lon, lat = self.projector.to_wgs84(x, y)
        return float(lon), float(lat)

    def lonlat_to_cell(self, lon: float, lat: float) -> tuple[int, int]:
        x, y = self.projector.to_local(lon, lat)
        j = int(round(x / self.cell_m + (self.nx - 1) / 2.0))
        i = int(round(y / self.cell_m + (self.ny - 1) / 2.0))
        return int(np.clip(i, 0, self.ny - 1)), int(np.clip(j, 0, self.nx - 1))

    def in_bounds(self, i: int, j: int) -> bool:
        return 0 <= i < self.ny and 0 <= j < self.nx

    # ── terrain derivatives ─────────────────────────────────────────────────────

    def slope_gradient(self) -> tuple[np.ndarray, np.ndarray]:
        """Uphill gradient (dz/dx east, dz/dy north) as rise/run fractions per cell."""
        gy, gx = np.gradient(self.elevation, self.cell_m)
        return gx, gy  # east, north components (uphill = +grad)

    # ── mask -> geometry ────────────────────────────────────────────────────────

    def mask_to_polygon(self, mask: np.ndarray, smooth: bool = True) -> BaseGeometry | None:
        """Union of burned cells -> a lon/lat polygon (or None if empty)."""
        if mask is None or not mask.any():
            return None
        ii, jj = np.nonzero(mask)
        half = self.cell_m / 2.0
        squares = []
        xs = self._xs[jj]
        ys = self._ys[ii]
        for x, y in zip(xs, ys, strict=False):
            squares.append(
                _square(x - half, y - half, x + half, y + half)
            )
        merged = unary_union(squares)
        if smooth and not merged.is_empty:
            # close small gaps and de-block the staircase edges a touch
            merged = merged.buffer(self.cell_m * 0.75).buffer(-self.cell_m * 0.75)
        merged = self.projector.geom_to_wgs84(merged)
        return merged if not merged.is_empty else None

    def ignition_mask(self, ignition_lonlat: tuple[float, float], radius_m: float = 0.0) -> np.ndarray:
        """Boolean mask of ignition cells for a point (optionally a small disk)."""
        i0, j0 = self.lonlat_to_cell(*ignition_lonlat)
        mask = np.zeros((self.ny, self.nx), dtype=bool)
        mask[i0, j0] = True
        if radius_m > 0:
            r = int(round(radius_m / self.cell_m))
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if di * di + dj * dj <= r * r and self.in_bounds(i0 + di, j0 + dj):
                        mask[i0 + di, j0 + dj] = True
        return mask


def _square(x0: float, y0: float, x1: float, y1: float):
    from shapely.geometry import Polygon

    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ── synthetic builder (offline demo; no network / no keys) ───────────────────────


def synthetic_grid(
    center_lat: float,
    center_lon: float,
    cell_m: float = 200.0,
    n: int = 120,
    *,
    wind_speed_ms: float = 8.0,
    wind_dir_to_deg: float = 45.0,
    base_fuel: int = 2,
    moisture: float = 0.06,
    seed: int = 7,
) -> FireGrid:
    """A plausible ridge-and-valley terrain with mixed fuels and a uniform wind, for the demo.

    Everything is clearly synthetic (CLAUDE.md principle 2); the demo labels it as such.
    """
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:n, 0:n].astype(float)  # xs = column (east), ys = row (north)
    # a ridge running NW-SE plus two hills -> real slope/aspect variation the fire must climb
    elevation = (
        300.0
        + 200.0 * np.sin((xs * 0.7 + ys * 0.3) / n * np.pi)
        + 170.0 * np.exp(-(((xs - n * 0.68) ** 2 + (ys - n * 0.62) ** 2) / (2 * (n * 0.13) ** 2)))
        + 110.0 * np.exp(-(((xs - n * 0.30) ** 2 + (ys - n * 0.30) ** 2) / (2 * (n * 0.10) ** 2)))
    )
    elevation += rng.normal(0, 5, size=elevation.shape)

    # Fuels: base fuel everywhere, with a faster chaparral band downwind, a grass band, and a
    # non-burnable river as a *downwind* barrier (with a gap) that the front must flow around.
    fuel = np.full((n, n), base_fuel, dtype=int)
    fuel[(ys > n * 0.62)] = 4  # chaparral to the north (faster)
    fuel[(xs < n * 0.18)] = 1  # short grass on the west edge
    # meandering non-burnable river near column 0.72n, with a gap between rows 0.42n–0.58n
    river_col = n * 0.72 + n * 0.05 * np.sin(ys / n * 2 * np.pi)
    river = (np.abs(xs - river_col) < 1.4) & ~((ys > n * 0.42) & (ys < n * 0.58))
    fuel[river] = 0

    windu = np.full((n, n), wind_speed_ms * np.sin(np.radians(wind_dir_to_deg)))
    windv = np.full((n, n), wind_speed_ms * np.cos(np.radians(wind_dir_to_deg)))
    moist = np.full((n, n), moisture)
    return FireGrid(center_lat, center_lon, cell_m, elevation, fuel, windu, windv, moist)
