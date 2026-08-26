"""Retrospective evaluation on a real historical fire (docs/EVALUATION.md §5).

Ground truth is the fire's **observed progression from GOES-18 ABI active-fire detections** — a real,
keyless, reproducible signal (the same active-fire labels WildfireSpreadTS uses). The protocol:

  1. Pre-register the fire, window, horizons, metrics, and thresholds (written to
     docs/EVALUATION_PREREG.md with the git sha) BEFORE any scoring.
  2. Pull the GOES fire-pixel time-series over the window; build a truth arrival-time raster.
  3. Assimilate GOES detections only up to the issue time (strict causal masking); forecast forward.
  4. Score ON vs OFF at horizons in the held-out window: perimeter IoU/Dice, Brier, coverage, and
     the evacuation lead-time delta.

Terrain (Terrain Tiles), fuels (ESA WorldCover), and wind (HRRR historical) are all real. The wind
*prior* is intentionally weak with a wide ensemble spread, so the ablation measures how much the
GOES assimilation resolves the spread — which is the whole thesis.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

from firewatch.config import EventPaths
from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.forecast.grid import FireGrid
from firewatch.ingest import assets, goes, hrrr, landfire
from firewatch.ingest import dem as demmod
from firewatch.ingest.base import BBox
from firewatch.ontology.objects import (
    Fire,
    FirePerimeter,
    FireStatus,
    PerimeterSource,
    PopulationZone,
    WeatherCell,
    new_id,
)
from firewatch.ontology.store import Store
from firewatch.pipeline import EventBundle, lead_time_analysis, run_pipeline, sharpening_series
from firewatch.report import generate_figures

log = logging.getLogger("firewatch.retro")


@dataclass
class RetroConfig:
    key: str
    name: str
    center_lon: float
    center_lat: float
    start_utc: str  # ISO; approximate ignition/discovery (GOES-18 era, >= 2023)
    window_min: int = 360  # total window over which truth is built
    assim_min: int = 180  # assimilate GOES up to here; score beyond
    horizons: list[int] = field(default_factory=lambda: [210, 240, 300, 360])
    cell_m: float = 300.0
    half_extent_m: float = 24000.0
    goes_steps: int = 16
    members: int = 40
    threshold: float = 0.5
    truth_disk_m: float = 1400.0


# Pre-registered fires (GOES-18 era, large well-observed California runs)
RETRO_REGISTRY: dict[str, RetroConfig] = {
    "park": RetroConfig(
        key="park", name="Park Fire (2024)", center_lon=-121.68, center_lat=39.87,
        start_utc="2024-07-24T22:00:00Z", window_min=360, assim_min=180,
        horizons=[210, 240, 300, 360], cell_m=300.0, half_extent_m=26000.0, goes_steps=16, members=40,
    ),
    "palisades": RetroConfig(
        key="palisades", name="Palisades Fire (2025)", center_lon=-118.55, center_lat=34.08,
        start_utc="2025-01-07T18:30:00Z", window_min=360, assim_min=180,
        horizons=[210, 240, 300, 360], cell_m=250.0, half_extent_m=16000.0, goes_steps=16, members=40,
    ),
    "eaton": RetroConfig(
        key="eaton", name="Eaton Fire (2025)", center_lon=-118.13, center_lat=34.19,
        start_utc="2025-01-08T02:30:00Z", window_min=360, assim_min=180,
        horizons=[210, 240, 300, 360], cell_m=250.0, half_extent_m=14000.0, goes_steps=16, members=40,
    ),
}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def write_prereg(cfg: RetroConfig) -> str:
    """Write the pre-registration BEFORE scoring (records git sha + timestamp)."""
    now = datetime.now(UTC)
    text = f"""# Retrospective pre-registration — {cfg.name}

*Committed BEFORE scoring (docs/EVALUATION.md §5). Ground truth = GOES-18 ABI active-fire progression.*

- **Fire:** {cfg.name}  (key: `{cfg.key}`)
- **Approx. center:** ({cfg.center_lat}, {cfg.center_lon})
- **Replay window (UTC):** {cfg.start_utc} + {cfg.window_min} min
- **Assimilation window:** first {cfg.assim_min} min (GOES only, strict causal masking)
- **Forecast horizons (min since first detection):** {cfg.horizons}  (all > assimilation window)
- **Skill metrics:** perimeter IoU, Sørensen–Dice, burn Brier score, coverage @50/80/90%
- **Decision metric:** evacuation lead-time delta @ confidence threshold = {cfg.threshold}
- **Baselines:** assimilation OFF (physical prior, no obs); persistence is implicit (early perimeter)
- **Ensemble:** {cfg.members} members, wide wind prior (direction σ=45°) so ON must earn its skill
- **Grid:** {cfg.cell_m:.0f} m cells, ±{cfg.half_extent_m/1000:.0f} km; DEM=Terrain Tiles, fuels=ESA WorldCover, wind=HRRR
- **Committed at:** {now.isoformat()}  ·  **git sha:** {_git_sha()}

> No forecast issued at time t uses any observation after t. Results are appended to
> `outputs/retro_{cfg.key}/results.json` and figures under `outputs/retro_{cfg.key}/figures/`.
"""
    from firewatch.config import REPO_ROOT

    out = REPO_ROOT / "docs" / "EVALUATION_PREREG.md"
    out.write_text(text)
    return str(out)


def _rasterize_points_disk(grid: FireGrid, pts_lonlat, radius_m: float) -> np.ndarray:
    mask = np.zeros((grid.ny, grid.nx), dtype=bool)
    r = int(round(radius_m / grid.cell_m))
    for lon, lat in pts_lonlat:
        i0, j0 = grid.lonlat_to_cell(lon, lat)
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if di * di + dj * dj <= r * r and grid.in_bounds(i0 + di, j0 + dj):
                    mask[i0 + di, j0 + dj] = True
    return mask


def build_retro_bundle(cfg: RetroConfig, store: Store) -> EventBundle:
    from firewatch.geo import from_geojson

    event_id = f"retro_{cfg.key}"
    t0 = datetime.fromisoformat(cfg.start_utc.replace("Z", "+00:00"))
    bbox = BBox.around(cfg.center_lon, cfg.center_lat, half_deg=cfg.half_extent_m / 111_320.0 * 1.15)

    # real terrain + fuels + historical wind
    d = demmod.fetch_dem(cfg.center_lat, cfg.center_lon, half_extent_m=cfg.half_extent_m, cell_m=cfg.cell_m, event_id=event_id)
    if d is None:
        from firewatch.terrain import DEM

        n = int(2 * cfg.half_extent_m / cfg.cell_m)
        d = DEM(cfg.center_lat, cfg.center_lon, cfg.cell_m, np.full((n, n), 500.0))
    fuelinfo = landfire.fetch_fuel(d, event_id=event_id, bbox=bbox)
    wind = hrrr.fetch_wind_hrrr(cfg.center_lat, cfg.center_lon, t0) or hrrr.fetch_wind(cfg.center_lat, cfg.center_lon)

    grid = FireGrid(center_lat=cfg.center_lat, center_lon=cfg.center_lon, cell_m=cfg.cell_m,
                    elevation=d.elevation, fuel=fuelinfo["fuel"],
                    wind_u=np.full(d.elevation.shape, wind["wind_u"]),
                    wind_v=np.full(d.elevation.shape, wind["wind_v"]),
                    moisture=np.full(d.elevation.shape, fuelinfo["moisture"]))

    # GOES active-fire time-series (real ground truth)
    raw = goes.fetch(bbox, t0, t0 + timedelta(minutes=cfg.window_min), fire_id="fire_" + event_id,
                     event_id=event_id, max_steps=cfg.goes_steps)
    raw = sorted([o for o in raw if o.geometry], key=lambda o: o.t)
    if not raw:
        raise SystemExit(f"no GOES fire pixels found for {cfg.name} in window — adjust config/window.")
    t0_eff = raw[0].t

    # truth arrival raster (minutes since first detection) + relabel obs times to t0_eff
    truth = np.full((grid.ny, grid.nx), np.inf)
    obs = []
    ignition = None
    for o in raw:
        minutes = (o.t - t0_eff).total_seconds() / 60.0
        g = from_geojson(o.geometry)
        pts = [(p.x, p.y) for p in (g.geoms if g.geom_type == "MultiPoint" else [g])]
        if ignition is None and pts:
            ignition = (float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts])))
        m = _rasterize_points_disk(grid, pts, cfg.truth_disk_m)
        truth[m & (minutes < truth)] = minutes
        o.t = t0_eff + timedelta(minutes=minutes)  # already, keep
        obs.append(o)

    initial_mask = _rasterize_points_disk(grid, [ignition], cfg.truth_disk_m) if ignition else None

    fire = Fire(id="fire_" + event_id, t=t0_eff, name=cfg.name, discovered_at=t0_eff, status=FireStatus.active,
                centroid={"type": "Point", "coordinates": list(ignition)},
                ignition_estimate={"type": "Point", "coordinates": list(ignition)})

    zones = assets.fetch_zones(bbox, event_id=event_id)
    roads = assets.fetch_roads(bbox, event_id=event_id)
    if not zones:
        from shapely.geometry import Point as _P

        from firewatch.geo import destination_point
        zones = [PopulationZone(id=f"zone_{i}", name=f"Sector {i+1}",
                                geometry=_P(*destination_point(*ignition, b, 12000)).buffer(0.02), population=1000)
                 for i, b in enumerate((30, 90, 150, 210, 300))]

    weather = WeatherCell(id="wx_0", t=t0_eff, bbox=list(bbox.as_tuple()), wind_u=wind["wind_u"],
                          wind_v=wind["wind_v"], rh=wind.get("rh_pct"), source=wind["source"])
    obs_perims = [FirePerimeter(id=new_id("perim"), t=t0_eff + timedelta(minutes=cfg.assim_min),
                                fire_id=fire.id,
                                geometry=grid.mask_to_polygon(truth <= cfg.assim_min),
                                source=PerimeterSource.observed)]
    obs_perims = [p for p in obs_perims if p.geometry]

    store.put(fire)
    store.put_many(zones + roads + [weather] + obs_perims + obs)

    note = (f"Retrospective on {cfg.name} — ground truth is GOES-18 ABI active-fire progression "
            f"(real, keyless). Terrain=Terrain Tiles; fuels={fuelinfo['source']}; wind={wind['source']}. "
            f"Assimilate GOES ≤ +{cfg.assim_min} min (causal), forecast/score beyond.")

    return EventBundle(event_id=event_id, store=store, grid=grid, dem=d, fire=fire,
                       ignition_lonlat=ignition, ignition_time=t0_eff, zones=zones, roads=roads,
                       structures=[], cameras=[], observations=obs,
                       wind={"speed_ms": wind["speed_ms"],
                             "dir_to_deg": (np.degrees(np.arctan2(wind["wind_u"], wind["wind_v"])) + 360) % 360,
                             "rh_pct": wind.get("rh_pct"), "source": wind["source"]},
                       truth_arrival=truth, initial_burned_mask=initial_mask, note=note)


def run_retrospective(key: str = "park") -> dict:
    import warnings
    warnings.simplefilter("ignore")
    cfg = RETRO_REGISTRY[key]
    prereg_path = write_prereg(cfg)  # BEFORE scoring
    log.info("pre-registration written: %s", prereg_path)

    paths = EventPaths(f"retro_{cfg.key}").ensure()
    if paths.ontology_db.exists():
        paths.ontology_db.unlink()
    store = Store(paths.ontology_db)
    bundle = build_retro_bundle(cfg, store)

    # wide-wind ensemble so the assimilation must earn its skill
    ecfg = EnsembleConfig(n_members=cfg.members, wind_dir_sd_deg=45.0, wind_mult_sd=0.4,
                          moisture_mult_sd=0.3, ignition_sd_m=cfg.cell_m * 2, spread_cap_ms=3.5)
    issue = bundle.ignition_time + timedelta(minutes=cfg.assim_min)
    result = run_pipeline(bundle, issue, ensemble_config=ecfg, horizons=cfg.horizons)

    offs = [int(cfg.assim_min * f) for f in (0.25, 0.5, 0.75, 1.0)]
    sharp = sharpening_series(bundle, offs, horizon=cfg.horizons[1],
                              cfg=EnsembleConfig(n_members=max(24, cfg.members // 2), wind_dir_sd_deg=45.0, wind_mult_sd=0.4))
    leads = lead_time_analysis(bundle, offs, horizon=cfg.horizons[-1], threshold=cfg.threshold,
                               cfg=EnsembleConfig(n_members=max(24, cfg.members // 2), wind_dir_sd_deg=45.0, wind_mult_sd=0.4))
    figs = generate_figures(bundle, result, sharp)

    results = {
        "fire": cfg.name, "key": cfg.key, "issue": issue.isoformat(),
        "ground_truth": "GOES-18 ABI active-fire progression",
        "skill_on": result.get("skill_on"), "skill_off": result.get("skill_off"),
        "calibration": figs["metrics"].get("calibration"),
        "lead_time": leads, "note": bundle.note,
        "feeds": sorted({o.provenance.source for o in bundle.observations}),
        "n_observations": len(bundle.observations),
    }
    (paths.outputs / "results.json").write_text(json.dumps(results, indent=2, default=str))
    _print(cfg, result, results)
    store.close()
    return results


def _print(cfg, result, results):
    print(f"\n{'='*74}\n🔥 FIREWATCH RETROSPECTIVE — {cfg.name}\n{'='*74}")
    print(f"ground truth: {results['ground_truth']} | {results['n_observations']} GOES detections")
    print(f"feeds: {', '.join(results['feeds'])}")
    so, sf = results["skill_on"], results["skill_off"]
    if so and sf:
        print("\nAssimilation ablation on REAL data (perimeter IoU vs GOES-observed fire):")
        print(f"  {'horizon':>9} {'OFF':>7} {'ON':>7} {'delta':>8}")
        for h in cfg.horizons:
            print(f"  {'+'+str(h)+'m':>9} {sf[h]['iou']:>7.3f} {so[h]['iou']:>7.3f} {so[h]['iou']-sf[h]['iou']:>+8.3f}")
        mo = np.mean([sf[h]["iou"] for h in cfg.horizons])
        mn = np.mean([so[h]["iou"] for h in cfg.horizons])
        print(f"  {'MEAN':>9} {mo:>7.3f} {mn:>7.3f} {mn-mo:>+8.3f}")
    cal = results.get("calibration")
    if cal:
        cov = cal["coverage"]
        print(f"\ncalibration @+{cal['horizon']}m: Brier {cal['brier_raw']:.3f}->{cal['brier_calibrated']:.3f} "
              f"| coverage 50/80/90 = {cov.get(0.5,float('nan')):.2f}/{cov.get(0.8,float('nan')):.2f}/{cov.get(0.9,float('nan')):.2f}")
    if results["lead_time"]:
        print("\nlead-time (earliest flag, ON vs OFF):")
        for L in results["lead_time"]:
            d = f"{L['lead_delta_min']:.0f} min earlier" if L.get("lead_delta_min") else ("ON only" if L.get("on_flag_min") is not None and L.get("off_flag_min") is None else "—")
            print(f"  {L['zone']:<18} truth@{L['truth_arrival_min']:.0f}m  ON:{L['on_flag_min']}  OFF:{L['off_flag_min']}  {d}" if L.get("truth_arrival_min") is not None else f"  {L['zone']:<18} not reached")
    print("=" * 74)
