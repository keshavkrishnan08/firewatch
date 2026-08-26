"""Showcase assets for the FIREWATCH site: a pipeline walkthrough (one figure + academic
description per stage), a results page of custom research graphs, and a demo overview video.

Everything is generated from real data (Park Fire GOES-18 replay + the real Pyronear smoke image
for the perception stage). Writes PNG/MP4 into docs/assets and a manifest to outputs/showcase.json.
"""
# ruff: noqa: E702  (compact `fig, ax = ...; style(ax)` figure lines are idiomatic here)
from __future__ import annotations

import json
import logging
import warnings

import numpy as np

from firewatch.config import REPO_ROOT

log = logging.getLogger("firewatch.showcase")
ASSETS = REPO_ROOT / "docs" / "assets"
BG = "#0b0d0f"
PANEL = "#11151a"
GRID = "#242a31"
TXT = "#e7eaed"
MUT = "#8a939e"
BLUE = "#4c9aff"
FIRE = "#ff6848"


def _style(ax, title=None):
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUT, labelsize=8)
    ax.grid(True, color=GRID, lw=0.5, alpha=0.5)
    if title:
        ax.set_title(title, color=TXT, fontsize=11, loc="left", pad=8)


# ── pipeline stages ──────────────────────────────────────────────────────────


PIPELINE = [
    ("ingest", "Ingest", "Heterogeneous public feeds → one ontology",
     "Ground/tower cameras, geostationary and polar-orbiting active-fire products, weather, terrain "
     "and fuels are pulled from open feeds (GOES-18 ABI, VIIRS/MODIS via FIRMS, NOAA HRRR, USGS/AWS "
     "Terrain Tiles, ESA WorldCover, NIFC perimeters, OpenStreetMap) and resolved into a single "
     "time-versioned ontology of `Observation` objects, each carrying mandatory provenance "
     "(source, product, retrieval time, native resolution). Modules exchange ontology objects, "
     "never raw payloads — the decoupling that makes the system auditable and reconstructable at "
     "any past instant."),
    ("perception", "Perception", "Detect + segment smoke/flame on imagery",
     "Camera frames pass through an off-the-shelf detector (YOLO / RT-DETR) and a promptable video "
     "segmenter (SAM 2), with a learned U-Net trained on real Pyronear wildfire imagery on the ML "
     "path and a transparent classical-CV fallback when weights are absent. Per-frame smoke-state "
     "features — mask area, centroid, bearing, growth rate, plume tilt (a wind proxy) — are emitted. "
     "Detection is a commodity input, not the contribution; the value is what happens downstream."),
    ("georeference", "Georeference", "Camera plume → lat/lon front + uncertainty",
     "Given a camera pose and a smoke mask, rays are cast through mask pixels and intersected with a "
     "DEM to recover ground coordinates of the plume base / fire front, with an uncertainty region "
     "propagated from pose, tilt and plume-base ambiguity. Imprecise PTZ tilt is self-calibrated by "
     "matching the imaged skyline to the DEM-rendered horizon, and ≥2 cameras triangulate for a "
     "tighter fix. The georeferenced front is emitted as an assimilable observation."),
    ("tracking", "Tracking", "Cluster detections → track the fire object",
     "At each timestep the active-fire pixels are clustered into fire objects (DBSCAN over a local "
     "metric projection) and associated across time by nearest-centroid data association — the core "
     "of multi-object tracking. From the track we derive the centroid path, growth curve, "
     "rate-of-spread and heading, giving a continuous, quantitative estimate of the fire's state "
     "from discrete satellite observations."),
    ("forecast", "Forecast", "Rothermel + minimum-travel-time ensemble",
     "A transparent physical prior propagates the front: Rothermel (1972) surface rate-of-spread "
     "over the 13 standard fuel models drives a minimum-travel-time (Dijkstra) solve with an "
     "elliptical directional ROS on the fuel/slope/wind grid. An ensemble of members with perturbed "
     "wind, fuel-moisture, ignition and ROS parameters represents forecast uncertainty; the weighted "
     "fraction of members that have burned a cell by a horizon IS the burn probability."),
    ("assimilation", "Assimilation", "Correct the ensemble from live observations",
     "A regularized particle filter corrects the ensemble toward incoming observations "
     "(GOES/VIIRS hotspots, camera fronts, official perimeters). Each member is scored by how well "
     "its predicted burned area matches the observation under a provenance-weighted, front-distance "
     "likelihood; members are reweighted and resampled with parameter jitter when the effective "
     "sample size collapses. A particle filter (vs. an EnKF) avoids the classic spurious-fire "
     "failure mode. This assimilation is the research core — it measurably sharpens the forecast."),
    ("calibration", "Calibration", "Make the probabilities mean what they say",
     "The burn-probability field is treated as a first-class calibrated product. Reliability "
     "diagrams, Brier score, CRPS and empirical coverage are computed against the observed "
     "progression; temperature scaling / isotonic recalibration are applied and reported pre/post. "
     "A cell assigned 30% should burn ~30% of the time, and the stated 90% region should contain "
     "the truth ~90% of the time — calibration is a deliverable, not an afterthought."),
    ("decision", "Decision", "Exposure & human-in-the-loop analysis",
     "The calibrated forecast is overlaid on population and assets (OpenStreetMap places, building "
     "footprints, road graph) to compute expected exposure, time-to-threat, and egress risk with "
     "confidence bands. Every output is traceable to the observations and forecast that produced it. "
     "The system informs a human decision — it never issues an autonomous order."),
]


def _park_bundle():
    from firewatch.forecast.tracking import track_from_observations
    from firewatch.ontology.store import Store
    from firewatch.retrospective import RETRO_REGISTRY, build_retro_bundle

    cfg = RETRO_REGISTRY["park"]
    b = build_retro_bundle(cfg, Store(":memory:"))
    return cfg, b, track_from_observations(b.observations, b.ignition_time)


def _hillshade(elev, cell_m):
    from firewatch.historical import _hillshade as hs

    return hs(elev, cell_m)


def pipeline_figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from firewatch.forecast.engine import run_forecast
    from firewatch.forecast.ensemble import EnsembleConfig
    from firewatch.forecast.spread import burned_mask
    from firewatch.forecast.tracking import _cluster
    from firewatch.geo import from_geojson

    cfg, b, track = _park_bundle()
    grid = b.grid
    proj = grid.projector
    ext = [grid._xs[0] / 1000, grid._xs[-1] / 1000, grid._ys[0] / 1000, grid._ys[-1] / 1000]
    hs = _hillshade(grid.elevation, grid.cell_m)
    goes = sorted([o for o in b.observations if o.kind.value == "goes" and o.geometry], key=lambda o: o.t)
    t0 = goes[0].t
    det = []
    for o in goes:
        g = from_geojson(o.geometry)
        for p in (g.geoms if g.geom_type == "MultiPoint" else [g]):
            det.append(((o.t - t0).total_seconds() / 60.0, p.x, p.y))
    det = np.array(det)

    def base(ax):
        ax.imshow(hs, origin="lower", cmap="gray", extent=ext, alpha=0.5, vmin=-0.2, vmax=1.2)
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.axis("off")

    def save(fig, name):
        p = ASSETS / f"stage_{name}.png"
        fig.savefig(p, dpi=130, facecolor=BG, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
        return p.name

    out = {}
    # ingest — detections over terrain, colored by time
    fig, ax = plt.subplots(figsize=(5, 5), facecolor=BG); base(ax)
    dl = np.array([proj.to_local(x, y) for x, y in det[:, 1:3]]) / 1000
    ax.scatter(dl[:, 0], dl[:, 1], c=det[:, 0], cmap="inferno", s=28, edgecolor="#ffdca8", linewidths=0.3)
    ax.set_title("GOES-18 active-fire detections", color=TXT, fontsize=10, loc="left")
    out["ingest"] = save(fig, "ingest")

    # perception — real Pyronear image + U-Net mask
    try:
        from firewatch.perception.smoke_net import load_if_available, load_pyro_sdis
        seg = load_if_available()
        data = load_pyro_sdis(n=8, n_neg=0, seed=7, log=lambda *_: None)
        img = next((im for im, mk in data if mk.any()), data[0][0])
        fig, ax = plt.subplots(figsize=(5, 3.6), facecolor=BG)
        rgb = img[..., ::-1].copy()
        if seg is not None:
            mask = seg.segment(img)
            rgb[mask] = (0.45 * rgb[mask] + 0.55 * np.array([76, 154, 255])).astype(np.uint8)
        ax.imshow(rgb); ax.axis("off")
        ax.set_title("Real tower-cam frame · learned smoke mask (blue)", color=TXT, fontsize=10, loc="left")
        out["perception"] = save(fig, "perception")
    except Exception as e:
        log.warning("perception stage figure skipped: %s", e)

    # georeference — schematic ray-cast over terrain profile
    fig, ax = plt.subplots(figsize=(5, 3.6), facecolor=BG); ax.set_facecolor(PANEL)
    xs = np.linspace(0, 10, 200)
    terr = 1.2 + 0.5 * np.sin(xs / 1.5) + 0.15 * xs
    ax.fill_between(xs, 0, terr, color="#2a3140")
    ax.plot([0.4], [terr[8] + 0.5], marker="v", color=BLUE, ms=12)
    for tx in (5.6, 6.2, 6.8):
        i = int(tx / 10 * 200)
        ax.plot([0.4, tx], [terr[8] + 0.5, terr[i]], color=BLUE, lw=1, alpha=0.5)
    ax.plot([6.2], [terr[124]], marker="*", color=FIRE, ms=18)
    ax.annotate("fire front\n(lat/lon ± cone)", (6.2, terr[124]), (7.2, terr[124] + 1.2), color=TXT, fontsize=8,
                arrowprops=dict(arrowstyle="-", color=MUT))
    ax.text(0.4, terr[8] + 0.75, " camera", color=BLUE, fontsize=8)
    ax.set_xlim(0, 10); ax.set_ylim(0, terr.max() + 1.6); ax.axis("off")
    ax.set_title("DEM ray-cast · camera → ground coordinates", color=TXT, fontsize=10, loc="left")
    out["georeference"] = save(fig, "georeference")

    # tracking — clusters + centroid path
    fig, ax = plt.subplots(figsize=(5, 5), facecolor=BG); base(ax)
    last = det[det[:, 0] <= det[:, 0].max()]
    clusters = _cluster([(x, y) for x, y in last[:, 1:3]])
    cols = ["#4c9aff", "#f2b84b", "#41d69a", "#c77dff"]
    for k, cl in enumerate(clusters):
        cl = np.array([proj.to_local(x, y) for x, y in cl]) / 1000
        ax.scatter(cl[:, 0], cl[:, 1], s=30, color=cols[k % 4], edgecolor="white", linewidths=0.3)
    path = np.array([proj.to_local(*p.centroid) for p in track.points]) / 1000
    ax.plot(path[:, 0], path[:, 1], color="#4ff0d0", lw=2.2)
    ax.scatter(path[:, 0], path[:, 1], s=18, color="#4ff0d0", zorder=5)
    ax.set_title("DBSCAN clusters + tracked centroid path", color=TXT, fontsize=10, loc="left")
    out["tracking"] = save(fig, "tracking")

    # forecast — burn probability field
    issue_mask = burned_mask(b.truth_arrival, cfg.assim_min)
    fc = run_forecast(grid, b.ignition_lonlat, b.ignition_time, assimilate=False, issued_at=b.ignition_time,
                      horizons=[cfg.window_min - cfg.assim_min], initial_mask=issue_mask,
                      ensemble_config=EnsembleConfig(n_members=36, wind_dir_sd_deg=28))
    p = fc.ensemble.burn_probability(cfg.window_min - cfg.assim_min)
    fig, ax = plt.subplots(figsize=(5, 5), facecolor=BG); base(ax)
    ax.imshow(np.where(p > 0.02, p, np.nan), origin="lower", extent=ext, cmap="YlOrRd", alpha=0.9, vmin=0, vmax=1)
    ax.set_title("Ensemble burn-probability field", color=TXT, fontsize=10, loc="left")
    out["forecast"] = save(fig, "forecast")

    # assimilation — ON vs OFF vs truth
    ecfg = EnsembleConfig(n_members=36, wind_dir_sd_deg=45, wind_mult_sd=0.4)
    from datetime import timedelta
    iss = b.ignition_time + timedelta(minutes=cfg.assim_min)
    on = run_forecast(grid, b.ignition_lonlat, b.ignition_time, observations=b.observations, assimilate=True,
                      issued_at=iss, horizons=cfg.horizons, ensemble_config=ecfg, initial_mask=b.initial_burned_mask)
    off = run_forecast(grid, b.ignition_lonlat, b.ignition_time, observations=b.observations, assimilate=False,
                       issued_at=iss, horizons=cfg.horizons, ensemble_config=ecfg, initial_mask=b.initial_burned_mask)
    h = cfg.horizons[-1]
    fig, ax = plt.subplots(figsize=(5, 5), facecolor=BG); base(ax)

    def draw(poly, **kw):
        if poly is None:
            return
        for pg in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
            if pg.is_empty or not hasattr(pg, "exterior"):
                continue
            x, y = proj.to_local(*np.asarray(pg.exterior.coords).T)
            ax.plot(x / 1000, y / 1000, **kw)
    draw(grid.mask_to_polygon(burned_mask(b.truth_arrival, h)), color="white", lw=1.6, ls="--", label="observed")
    draw(off.expected_perimeter[h], color=MUT, lw=1.6, label="baseline")
    draw(on.expected_perimeter[h], color=BLUE, lw=2.0, label="assimilation")
    ax.legend(loc="upper right", fontsize=7, facecolor=PANEL, edgecolor=GRID, labelcolor=TXT)
    ax.set_title("Assimilation ON vs OFF vs observed", color=TXT, fontsize=10, loc="left")
    out["assimilation"] = save(fig, "assimilation")

    # calibration — reliability diagram
    from firewatch.forecast.calibrate import (
        brier_score,
        fit_temperature,
        reliability_curve,
        temperature_scale,
    )
    pf = on.prob_fields[h].ravel()
    y = burned_mask(b.truth_arrival, h).ravel().astype(float)
    T = fit_temperature(pf, y); pc = temperature_scale(pf, T)
    rc, rc2 = reliability_curve(pf, y, 10), reliability_curve(pc, y, 10)
    fig, ax = plt.subplots(figsize=(5, 4.4), facecolor=BG); _style(ax, "Reliability diagram")
    ax.plot([0, 1], [0, 1], "--", color=MUT, lw=1)
    ax.plot(rc.pred_mean, rc.obs_freq, "o-", color=MUT, label=f"raw (Brier {brier_score(pf, y):.3f})")
    ax.plot(rc2.pred_mean, rc2.obs_freq, "o-", color=BLUE, label=f"calibrated (Brier {brier_score(pc, y):.3f})")
    ax.set_xlabel("predicted probability", color=MUT, fontsize=8)
    ax.set_ylabel("observed frequency", color=MUT, fontsize=8)
    ax.legend(fontsize=7, facecolor=PANEL, edgecolor=GRID, labelcolor=TXT)
    out["calibration"] = save(fig, "calibration")

    # decision — reuse the response poster if present
    rp = ASSETS / "response_poster_park.png"
    out["decision"] = rp.name if rp.exists() else None
    return out


# ── results graphs ───────────────────────────────────────────────────────────


def results_figures(events):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def save(fig, name):
        p = ASSETS / f"result_{name}.png"
        fig.savefig(p, dpi=130, facecolor=BG, bbox_inches="tight", pad_inches=0.12)
        plt.close(fig)
        return p.name

    out = {}
    cols = {"park": FIRE, "palisades": BLUE, "eaton": "#41d69a"}

    # growth curves
    fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=BG); _style(ax, "Tracked fire extent over time")
    for e in events:
        ev = e.get("evolution", [])
        if ev:
            ax.plot([f["t_min"] for f in ev], [f["area_km2"] for f in ev], "-o", ms=3, lw=1.8,
                    color=cols.get(e["key"], TXT), label=e["name"].split(" (")[0])
    ax.set_xlabel("minutes since first detection", color=MUT, fontsize=8)
    ax.set_ylabel("extent (km²)", color=MUT, fontsize=8)
    ax.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID, labelcolor=TXT)
    out["growth"] = save(fig, "growth")

    # model performance — grouped bars per horizon (mean across fires)
    hs = [s["horizon_min"] for s in events[0].get("skill_by_horizon", [])]
    if hs:
        base = np.array([np.mean([[s for s in e["skill_by_horizon"] if s["horizon_min"] == h][0]["iou_off"]
                                  for e in events]) for h in hs])
        assim = np.array([np.mean([[s for s in e["skill_by_horizon"] if s["horizon_min"] == h][0]["iou_on"]
                                    for e in events]) for h in hs])
        fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=BG); _style(ax, "Forecast skill vs GOES-observed perimeter (mean IoU)")
        x = np.arange(len(hs))
        ax.bar(x - 0.19, base, 0.36, color=MUT, label="baseline")
        ax.bar(x + 0.19, assim, 0.36, color=BLUE, label="assimilation")
        ax.set_xticks(x, [f"+{h // 60}h" if h >= 60 else f"+{h}m" for h in hs])
        ax.set_ylabel("IoU", color=MUT, fontsize=8)
        ax.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID, labelcolor=TXT)
        out["performance"] = save(fig, "performance")

    # detections cumulative
    fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=BG); _style(ax, "Cumulative GOES fire-pixel detections")
    for e in events:
        obs = e.get("observations", [])
        if obs:
            t = list(range(len(obs)))
            cum = np.cumsum([o["n_pixels"] for o in obs])
            ax.plot(np.array(t) * (e.get("window_min", 360) / max(1, len(obs) - 1)), cum, "-", lw=1.8,
                    color=cols.get(e["key"], TXT), label=e["name"].split(" (")[0])
    ax.set_xlabel("minutes since first detection", color=MUT, fontsize=8)
    ax.set_ylabel("cumulative pixels", color=MUT, fontsize=8)
    ax.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID, labelcolor=TXT)
    out["detections"] = save(fig, "detections")
    return out


# ── demo video (overview) ────────────────────────────────────────────────────


def demo_video(key="park"):
    import imageio.v2 as imageio

    tr = ASSETS / f"track_{key}.mp4"
    rs = ASSETS / f"response_{key}.mp4"
    if not tr.exists():
        return None
    frames = []
    for src in (tr, rs):
        if src.exists():
            for f in imageio.get_reader(src):
                frames.append(np.asarray(f))
    out = ASSETS / "demo.mp4"
    imageio.mimwrite(out, frames, fps=6, codec="libx264", quality=9, macro_block_size=16,
                     output_params=["-pix_fmt", "yuv420p"])
    return out.name


def build_showcase():
    warnings.simplefilter("ignore")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    events = json.loads((REPO_ROOT / "outputs" / "historical.json").read_text())
    log.info("generating pipeline figures…")
    stages = pipeline_figures()
    log.info("generating results graphs…")
    results = results_figures(events)
    log.info("assembling demo video…")
    demo = demo_video("park")
    manifest = {
        "demo": demo,
        "pipeline": [{"id": sid, "title": t, "subtitle": st, "desc": d, "figure": stages.get(sid)}
                     for (sid, t, st, d) in PIPELINE],
        "results": results,
    }
    (REPO_ROOT / "outputs" / "showcase.json").write_text(json.dumps(manifest, indent=2))
    log.info("showcase: %d stages, %d result graphs, demo=%s", len(PIPELINE), len(results), demo)
    return manifest


if __name__ == "__main__":
    build_showcase()
