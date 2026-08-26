"""A bank of real California landscapes (terrain + fuels) for training the spread surrogate.

Instead of self-distilling the physical model on synthetic grids, we sample random windows from real
DEM (AWS Terrain Tiles) + real ESA WorldCover fuels across diverse California wildland sites. The
surrogate then learns to emulate the physics prior on *real* landscapes — the training inputs are no
longer synthetic (only the wind/moisture forcings are randomized, exactly as an ensemble perturbs them).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from firewatch.config import REPO_ROOT

log = logging.getLogger("firewatch.landscapes")

# diverse California wildland sites (lat, lon)
SITES = [
    (39.90, -121.62), (34.22, -117.20), (34.10, -118.52), (38.52, -122.55), (36.60, -118.80),
    (40.55, -123.05), (33.32, -116.78), (37.30, -119.60), (34.52, -119.80), (35.32, -120.55),
    (41.30, -122.30), (36.22, -121.70),
]
BANK_PATH = REPO_ROOT / "data" / "models" / "landscape_bank.npz"


def build_landscape_bank(npz_path: Path = BANK_PATH, half_extent_m: float = 18000.0,
                         cell_m: float = 200.0, sites=None) -> Path:
    """Fetch real DEM + WorldCover for each site and cache as an .npz landscape bank."""
    from firewatch.ingest import dem as demmod
    from firewatch.ingest.landfire import fetch_worldcover

    sites = sites or SITES
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    store: dict[str, np.ndarray] = {}
    n_ok = 0
    for i, (lat, lon) in enumerate(sites):
        d = demmod.fetch_dem(lat, lon, half_extent_m=half_extent_m, cell_m=cell_m, event_id=f"land_{i}")
        if d is None or d.elevation.std() < 1:
            continue
        fuel = fetch_worldcover(d, event_id=f"land_{i}")
        if fuel is None or (fuel > 0).mean() < 0.05:
            continue
        store[f"elev_{n_ok}"] = d.elevation.astype(np.float32)
        store[f"fuel_{n_ok}"] = fuel.astype(np.int16)
        store[f"meta_{n_ok}"] = np.array([lat, lon, cell_m], dtype=np.float64)
        n_ok += 1
        log.info("landscape %d/%d cached (%s) elev %.0f-%.0f m", n_ok, len(sites),
                 f"{lat:.2f},{lon:.2f}", d.elevation.min(), d.elevation.max())
    if n_ok == 0:
        raise SystemExit("could not fetch any real landscapes (network?)")
    store["count"] = np.array([n_ok])
    np.savez_compressed(npz_path, **store)
    log.info("landscape bank: %d real sites -> %s", n_ok, npz_path)
    return npz_path


def load_bank(npz_path: Path = BANK_PATH) -> list[dict]:
    if not Path(npz_path).exists():
        return []
    z = np.load(npz_path)
    n = int(z["count"][0])
    out = []
    for i in range(n):
        lat, lon, cell = z[f"meta_{i}"]
        out.append({"elev": z[f"elev_{i}"], "fuel": z[f"fuel_{i}"], "lat": float(lat),
                    "lon": float(lon), "cell_m": float(cell)})
    return out
