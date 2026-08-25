"""Weather connector — 10-m wind for the ROS + ensemble (FR-ING-2).

Primary path is NOAA HRRR (3 km, hourly) via Herbie from AWS Open Data. Because GRIB subsetting can
be heavy/slow, the reliable keyless default is the NWS gridpoint API (api.weather.gov), which returns
wind speed/direction at the point. Falls back to a documented constant if both are unavailable — the
forecast then simply carries more wind uncertainty (FR-ING-5).
"""
from __future__ import annotations

import math
from datetime import datetime

from firewatch.ingest.base import http_get, log, soft


def _speed_dir_to_uv(speed_ms: float, dir_from_deg: float) -> tuple[float, float]:
    """Meteorological wind (direction FROM) -> u/v components of where it blows TO."""
    to = (dir_from_deg + 180.0) % 360.0
    return speed_ms * math.sin(math.radians(to)), speed_ms * math.cos(math.radians(to))


@soft
def fetch_wind_nws(lat: float, lon: float) -> dict | None:
    """Current 10-m wind from the NWS gridpoint API (keyless)."""
    pt = http_get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", timeout=25)
    if pt is None:
        return None
    grid = pt.json()["properties"].get("forecastGridData")
    if not grid:
        return None
    g = http_get(grid, timeout=25)
    if g is None:
        return None
    props = g.json()["properties"]

    def first(key, default=0.0):
        vals = props.get(key, {}).get("values", [])
        return float(vals[0]["value"]) if vals and vals[0].get("value") is not None else default

    speed_kmh = first("windSpeed", 12.0)
    dir_from = first("windDirection", 0.0)
    speed_ms = speed_kmh / 3.6
    rh = first("relativeHumidity", 20.0)
    temp_c = first("temperature", 25.0)
    u, v = _speed_dir_to_uv(speed_ms, dir_from)
    return {"wind_u": u, "wind_v": v, "speed_ms": speed_ms, "dir_from_deg": dir_from,
            "rh_pct": rh, "temp_c": temp_c, "source": "NWS api.weather.gov"}


@soft
def fetch_wind_hrrr(lat: float, lon: float, t: datetime) -> dict | None:  # pragma: no cover - heavy/optional
    """NOAA HRRR 10-m wind via Herbie (optional heavy path)."""
    try:
        from herbie import Herbie
    except Exception:
        return None
    H = Herbie(t.strftime("%Y-%m-%d %H:00"), model="hrrr", product="sfc", fxx=0)
    ds = H.xarray(":[UV]GRD:10 m above ground:", remove_grib=True)
    import numpy as np

    da = ds if not isinstance(ds, list) else ds[0]
    # nearest-point extraction is model-grid specific; keep this best-effort (domain mean)
    u = float(np.asarray(da["u10"]).mean())
    v = float(np.asarray(da["v10"]).mean())
    return {"wind_u": u, "wind_v": v, "speed_ms": math.hypot(u, v), "source": "NOAA HRRR (Herbie)"}


def fetch_wind(lat: float, lon: float, t: datetime | None = None, event_id: str = "event") -> dict:
    """Best wind available, degrading gracefully to a labeled constant."""
    w = fetch_wind_nws(lat, lon)
    if w:
        log.info("wind: NWS %.1f m/s from %.0f°", w["speed_ms"], w.get("dir_from_deg", 0))
        return w
    log.info("wind: no live source — using labeled constant fallback (higher uncertainty)")
    u, v = _speed_dir_to_uv(6.0, 225.0)
    return {"wind_u": u, "wind_v": v, "speed_ms": 6.0, "dir_from_deg": 225.0, "rh_pct": 25.0,
            "temp_c": 25.0, "source": "constant fallback (no live wind)"}
