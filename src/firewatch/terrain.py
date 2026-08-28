"""Digital Elevation Model sampler, the ray-cast surface for georeferencing and the slope term
for spread. Backed by a numpy array in a local meter frame with bilinear sampling; can be built
from a synthetic grid (demo) or a rasterio DEM (real 3DEP/SRTM ingest)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from firewatch.geo import Projector


@dataclass
class DEM:
    """Elevation raster with a local azimuthal-equidistant frame centered on (center_lat, center_lon).

    `elevation[i, j]` is meters at row i (north+) / col j (east+); cell spacing is `cell_m`.
    """

    center_lat: float
    center_lon: float
    cell_m: float
    elevation: np.ndarray

    def __post_init__(self) -> None:
        self.ny, self.nx = self.elevation.shape
        self.projector = Projector(self.center_lat, self.center_lon)
        self._x0 = -(self.nx - 1) / 2.0 * self.cell_m
        self._y0 = -(self.ny - 1) / 2.0 * self.cell_m

    # ── sampling ─────────────────────────────────────────────────────────────────

    def sample_local(self, x: float, y: float) -> float:
        """Bilinearly sample elevation at local meters (x east, y north). Edge-clamped."""
        fj = (x - self._x0) / self.cell_m
        fi = (y - self._y0) / self.cell_m
        j0 = int(np.floor(fj))
        i0 = int(np.floor(fi))
        if i0 < 0 or j0 < 0 or i0 >= self.ny - 1 or j0 >= self.nx - 1:
            ii = int(np.clip(round(fi), 0, self.ny - 1))
            jj = int(np.clip(round(fj), 0, self.nx - 1))
            return float(self.elevation[ii, jj])
        di = fi - i0
        dj = fj - j0
        e = self.elevation
        return float(
            e[i0, j0] * (1 - di) * (1 - dj)
            + e[i0, j0 + 1] * (1 - di) * dj
            + e[i0 + 1, j0] * di * (1 - dj)
            + e[i0 + 1, j0 + 1] * di * dj
        )

    def sample_lonlat(self, lon: float, lat: float) -> float:
        x, y = self.projector.to_local(lon, lat)
        return self.sample_local(x, y)

    def local_to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        lon, lat = self.projector.to_wgs84(x, y)
        return float(lon), float(lat)

    def lonlat_to_local(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.projector.to_local(lon, lat)
        return float(x), float(y)

    @property
    def max_extent_m(self) -> float:
        return max(self.nx, self.ny) * self.cell_m

    # ── builders ─────────────────────────────────────────────────────────────────

    @classmethod
    def from_grid(cls, grid) -> DEM:
        """Reuse a FireGrid's elevation as a DEM (demo path)."""
        return cls(grid.center_lat, grid.center_lon, grid.cell_m, grid.elevation.copy())

    @classmethod
    def from_rasterio(cls, path: str, center_lat: float, center_lon: float, half_extent_m: float = 15000.0, cell_m: float = 30.0) -> DEM:
        """Sample a rasterio-readable DEM into a local meter grid around a center (real ingest)."""
        import rasterio
        from rasterio.warp import transform as rio_transform

        proj = Projector(center_lat, center_lon)
        n = int(2 * half_extent_m / cell_m)
        xs = (np.arange(n) - (n - 1) / 2.0) * cell_m
        ys = (np.arange(n) - (n - 1) / 2.0) * cell_m
        XX, YY = np.meshgrid(xs, ys)
        lon, lat = proj.to_wgs84(XX.ravel(), YY.ravel())
        with rasterio.open(path) as ds:
            xx, yy = rio_transform("EPSG:4326", ds.crs, list(lon), list(lat))
            vals = np.array(list(ds.sample(list(zip(xx, yy, strict=False)))), dtype=float).ravel()
        elev = np.nan_to_num(vals.reshape(n, n), nan=float(np.nanmedian(vals)))
        return cls(center_lat, center_lon, cell_m, elev)
