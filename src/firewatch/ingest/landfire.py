"""Fuels connector, real LANDFIRE fuel models, with a documented heuristic fallback (FR-ING-2).

Primary path pulls a LANDFIRE fire-behavior fuel-model raster (Scott & Burgan 40 / Anderson 13) for
the fire's bbox from the LANDFIRE Product Service (LFPS async geoprocessing), reprojects to the local
grid, and maps the codes onto the 13 standard Anderson models the Rothermel core uses. If LFPS is
slow/unreachable, it falls back to a transparent elevation/slope heuristic, clearly labeled, so a
forecast always runs. Provenance records which path was used (honesty; NFR-4).
"""
from __future__ import annotations

import io
import time
import zipfile

import numpy as np

from firewatch.ingest.base import BBox, cache_dir, http_get, log
from firewatch.terrain import DEM

_LFPS = "https://lfps.usgs.gov/arcgis/rest/services/LandfireProductService/GPServer/LandfireProductService"
# candidate fuel products, newest first (Anderson-13 preferred; Scott&Burgan-40 as fallback)
_LAYERS = ["240FBFM13", "230FBFM13", "220FBFM13", "240FBFM40", "230FBFM40"]

# Scott & Burgan 40 -> Anderson 13 crosswalk (grouped by 40-model family)
_SB40_TO_A13 = {}
for c in range(91, 100):
    _SB40_TO_A13[c] = 0  # non-burnable
for c in range(101, 110):  # GR1-9 grass
    _SB40_TO_A13[c] = 1 if c <= 102 else (2 if c <= 104 else 3)
for c in range(121, 125):  # GS1-4 grass-shrub
    _SB40_TO_A13[c] = 2
for c in range(141, 150):  # SH1-9 shrub
    _SB40_TO_A13[c] = 5 if c <= 144 else 4
for c in range(161, 166):  # TU1-5 timber-understory
    _SB40_TO_A13[c] = 10
for c in range(181, 190):  # TL1-9 timber-litter
    _SB40_TO_A13[c] = 8 if c <= 182 else 9
for c in range(201, 205):  # SB1-4 slash-blowdown
    _SB40_TO_A13[c] = 11 + min(c - 201, 2)


def _map_codes(arr: np.ndarray) -> np.ndarray:
    """Auto-detect FBFM13 vs FBFM40 and map to Anderson 1-13 (0 = non-burnable)."""
    a = np.asarray(arr)
    out = np.zeros(a.shape, dtype=int)
    finite = np.isfinite(a)
    vmax = a[finite].max() if finite.any() else 0
    if vmax <= 20:  # Anderson 13 (or nodata/non-burnable 91-99 already excluded)
        m = (a >= 1) & (a <= 13)
        out[m] = a[m].astype(int)
    else:  # Scott & Burgan 40
        lut = np.zeros(int(max(210, vmax)) + 1, dtype=int)
        for k, v in _SB40_TO_A13.items():
            if k < len(lut):
                lut[k] = v
        idx = np.clip(np.nan_to_num(a, nan=0).astype(int), 0, len(lut) - 1)
        out = lut[idx]
    return out


def _submit_and_download(bbox: BBox, layer: str, event_id: str, timeout_s: float = 200.0) -> bytes | None:
    aoi = f"{bbox.minlon} {bbox.minlat} {bbox.maxlon} {bbox.maxlat}"
    r = http_get(f"{_LFPS}/submitJob", params={
        "Layer_List": layer, "Area_of_Interest": aoi, "Output_Projection": "4326", "f": "json",
    }, timeout=40)
    if r is None:
        return None
    try:
        job_id = r.json()["jobId"]
    except (KeyError, ValueError):
        return None
    log.info("LANDFIRE: submitted %s job %s", layer, job_id)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        s = http_get(f"{_LFPS}/jobs/{job_id}", params={"f": "json"}, timeout=30)
        if s is None:
            return None
        status = s.json().get("jobStatus")
        if status == "esriJobSucceeded":
            break
        if status in ("esriJobFailed", "esriJobCancelled", "esriJobTimedOut"):
            log.info("LANDFIRE: job %s -> %s", job_id, status)
            return None
        time.sleep(6)
    else:
        return None
    res = http_get(f"{_LFPS}/jobs/{job_id}/results/Output_File", params={"f": "json"}, timeout=30)
    if res is None:
        return None
    url = res.json().get("value", {}).get("url")
    if not url:
        return None
    z = http_get(url, timeout=90)
    return z.content if z is not None else None


def fetch_fbfm(bbox: BBox, dem: DEM, event_id: str = "event") -> np.ndarray | None:
    """Real LANDFIRE fuel-model array on the DEM grid (Anderson 1-13), or None on failure."""
    from rasterio.io import MemoryFile
    from rasterio.warp import transform as rio_transform

    cached = cache_dir(event_id) / "landfire_fbfm.tif"
    content = None
    if cached.exists():
        content = cached.read_bytes()
    else:
        for layer in _LAYERS:
            zbytes = _submit_and_download(bbox, layer, event_id)
            if not zbytes:
                continue
            try:
                zf = zipfile.ZipFile(io.BytesIO(zbytes))
                tif = next(n for n in zf.namelist() if n.lower().endswith(".tif"))
                content = zf.read(tif)
                cached.write_bytes(content)
                log.info("LANDFIRE: got %s (%s)", layer, tif)
                break
            except (zipfile.BadZipFile, StopIteration):
                continue
    if content is None:
        return None

    with MemoryFile(content) as mem, mem.open() as ds:
        n = dem.elevation.shape[0]
        xs = (np.arange(n) - (n - 1) / 2.0) * dem.cell_m
        ys = (np.arange(n) - (n - 1) / 2.0) * dem.cell_m
        XX, YY = np.meshgrid(xs, ys)
        lon, lat = dem.projector.to_wgs84(XX.ravel(), YY.ravel())
        if str(ds.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
            xx, yy = rio_transform("EPSG:4326", ds.crs, list(lon), list(lat))
        else:
            xx, yy = list(lon), list(lat)
        vals = np.array(list(ds.sample(list(zip(xx, yy, strict=False)))), dtype=float).ravel()
        vals[vals < 0] = np.nan
        return _map_codes(vals.reshape(n, n))


# ESA WorldCover 2021 (10 m, keyless COG on AWS) land-cover class -> Anderson 13 fuel model
_WC_TO_A13 = {10: 10, 20: 5, 30: 1, 40: 1, 50: 0, 60: 0, 70: 0, 80: 0, 90: 2, 95: 0, 100: 0}


def fetch_worldcover(dem: DEM, event_id: str = "event") -> np.ndarray | None:
    """Real fuels from ESA WorldCover 10 m land cover (AWS Open Data), mapped to Anderson 13."""
    import math

    import rasterio

    lat0, lon0 = dem.center_lat, dem.center_lon
    tlat = int(math.floor(lat0 / 3) * 3)
    tlon = int(math.floor(lon0 / 3) * 3)
    tile = f"{'N' if tlat >= 0 else 'S'}{abs(tlat):02d}{'W' if tlon < 0 else 'E'}{abs(tlon):03d}"
    url = f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    n = dem.elevation.shape[0]
    xs = (np.arange(n) - (n - 1) / 2.0) * dem.cell_m
    ys = (np.arange(n) - (n - 1) / 2.0) * dem.cell_m
    XX, YY = np.meshgrid(xs, ys)
    lon, lat = dem.projector.to_wgs84(XX.ravel(), YY.ravel())
    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_DISABLE_READDIR_ON_OPEN="YES"):
        with rasterio.open(f"/vsicurl/{url}") as ds:
            vals = np.array([v[0] for v in ds.sample(list(zip(lon, lat, strict=False)))], dtype=float)
    lut = np.zeros(101, dtype=int)
    for k, v in _WC_TO_A13.items():
        lut[k] = v
    idx = np.clip(np.nan_to_num(vals, nan=0).astype(int), 0, 100)
    fuel = lut[idx].reshape(n, n)
    # steep shrub -> chaparral (faster) using the DEM slope
    gy, gx = np.gradient(dem.elevation, dem.cell_m)
    fuel[(fuel == 5) & (np.hypot(gx, gy) > 0.5)] = 4
    return fuel


def fetch_fuel(dem: DEM, event_id: str = "event", seed: int = 3, bbox: BBox | None = None) -> dict:
    """Return {'fuel', 'moisture', 'source'}. Cascade: LANDFIRE FBFM -> ESA WorldCover -> heuristic."""
    if bbox is not None:
        try:
            fuel = fetch_fbfm(bbox, dem, event_id=event_id)
        except Exception as e:  # graceful
            log.warning("LANDFIRE fetch failed (%s)", e)
            fuel = None
        if fuel is not None and (fuel > 0).mean() > 0.05:
            log.info("fuels: real LANDFIRE fuel models, present: %s", sorted(set(np.unique(fuel).tolist())))
            return {"fuel": fuel, "moisture": 0.07, "source": "LANDFIRE FBFM (Anderson-13 mapped)"}

    # real satellite land cover (reliable, keyless)
    try:
        wc = fetch_worldcover(dem, event_id=event_id)
    except Exception as e:
        log.warning("WorldCover fetch failed (%s), using heuristic", e)
        wc = None
    if wc is not None and (wc > 0).mean() > 0.05:
        log.info("fuels: real ESA WorldCover land-cover fuels, present: %s", sorted(set(np.unique(wc).tolist())))
        return {"fuel": wc, "moisture": 0.07, "source": "ESA WorldCover 10m land cover (Anderson-13 mapped)"}

    # heuristic fallback (elevation/slope)
    rng = np.random.default_rng(seed)
    elev = dem.elevation
    gy, gx = np.gradient(elev, dem.cell_m)
    slope = np.hypot(gx, gy)
    fuel = np.full(elev.shape, 2, dtype=int)
    lo, hi = np.percentile(elev, [30, 75])
    fuel[elev < lo] = 1
    fuel[(elev >= lo) & (elev < hi)] = 5
    fuel[elev >= hi] = 10
    fuel[slope > 0.6] = 4
    verylow = elev < np.percentile(elev, 3)
    fuel[verylow & (rng.random(elev.shape) < 0.5)] = 0
    log.info("fuels: heuristic fuel field (LANDFIRE unavailable), models: %s", sorted(set(np.unique(fuel).tolist())))
    return {"fuel": fuel, "moisture": 0.07, "source": "estimated (elevation/slope heuristic; LANDFIRE unavailable)"}
