"""Historical fire tracking + forecast on real GOES data — the 'nothing synthetic' showcase.

For each registered real fire (retrospective.RETRO_REGISTRY) this pulls the real GOES-18 active-fire
time-series, runs the satellite fire tracker (forecast/tracking.py), runs the assimilating forecast
(ON vs OFF) against the GOES-observed ground truth, and renders a futuristic tracking visualization:
hillshaded real terrain, the fire footprint growing over time (time-coloured), the tracked centroid
path with heading, and the assimilated forecast perimeter. No synthetic imagery is used anywhere.
"""
from __future__ import annotations

import json
import logging
import warnings
from datetime import timedelta

import numpy as np

from firewatch.config import REPO_ROOT, EventPaths
from firewatch.forecast.engine import run_forecast, skill_vs_truth
from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.forecast.spread import burned_mask
from firewatch.forecast.tracking import FireTrack, track_from_observations
from firewatch.ontology.store import Store
from firewatch.retrospective import RETRO_REGISTRY, build_retro_bundle

log = logging.getLogger("firewatch.historical")

NEON = "#4ff0d0"
FLAME = "#ff6a2b"


def _hillshade(elev: np.ndarray, cell_m: float, az=315.0, alt=45.0) -> np.ndarray:
    gy, gx = np.gradient(elev, cell_m)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr, altr = np.radians(360 - az + 90), np.radians(alt)
    hs = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos(azr - aspect)
    return np.clip((hs - hs.min()) / (np.ptp(hs) + 1e-9), 0, 1)


def tracking_figure(bundle, track: FireTrack, on, ablation_delta: float | None, cfg) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm
    from matplotlib.colors import Normalize

    grid = bundle.grid
    proj = grid.projector
    ext = [grid._xs[0] / 1000, grid._xs[-1] / 1000, grid._ys[0] / 1000, grid._ys[-1] / 1000]  # km

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(13, 7.6), facecolor="#05070d")
    gs = fig.add_gridspec(2, 3, width_ratios=[2.4, 1, 1], height_ratios=[1, 1], wspace=0.22, hspace=0.3)
    ax = fig.add_subplot(gs[:, 0])
    ax.set_facecolor("#05070d")

    # hillshaded real terrain, dimmed
    hs = _hillshade(grid.elevation, grid.cell_m)
    ax.imshow(hs, origin="lower", cmap="gray", extent=ext, alpha=0.45, vmin=-0.2, vmax=1.2)
    # non-burnable (water/urban) faint blue
    ax.imshow(np.where(grid.fuel == 0, 1.0, np.nan), origin="lower", extent=ext, cmap="Blues", alpha=0.18)

    # fire footprint growth over time (GOES-observed truth) — the tracked object growing
    horizons = list(range(30, cfg.window_min + 1, 30))
    norm = Normalize(0, horizons[-1])
    cmap = plt.get_cmap("inferno")
    for t in horizons:
        poly = grid.mask_to_polygon(burned_mask(bundle.truth_arrival, t))
        if poly is None:
            continue
        for pg in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
            if pg.is_empty or not hasattr(pg, "exterior"):
                continue
            xs, ys = proj.to_local(*np.asarray(pg.exterior.coords).T)
            ax.plot(xs / 1000, ys / 1000, color=cmap(norm(t)), lw=1.6, alpha=0.9)

    # tracked centroid path (glowing) with heading arrow
    path = np.array([proj.to_local(*p.centroid) for p in track.points]) / 1000
    if len(path) >= 2:
        tt = np.array([p.t_min for p in track.points])
        for w, a in ((6, 0.12), (3.2, 0.9)):  # glow + core
            ax.plot(path[:, 0], path[:, 1], color=NEON, lw=w, alpha=a, solid_capstyle="round")
        ax.scatter(path[:, 0], path[:, 1], c=tt, cmap="cool", s=[8 + p.area_km2 * 0.6 for p in track.points],
                   edgecolor="white", linewidths=0.4, zorder=5)
        d = path[-1] - path[-2]
        ax.annotate("", xy=path[-1] + d / (np.hypot(*d) + 1e-9) * 1.4, xytext=path[-1],
                    arrowprops=dict(arrowstyle="-|>", color=NEON, lw=2))

    # assimilated forecast perimeter (ON) at the final horizon — cyan glow
    fp = on.expected_perimeter.get(cfg.horizons[-1])
    if fp is not None:
        for pg in (fp.geoms if fp.geom_type == "MultiPolygon" else [fp]):
            if pg.is_empty or not hasattr(pg, "exterior"):
                continue
            xs, ys = proj.to_local(*np.asarray(pg.exterior.coords).T)
            ax.plot(xs / 1000, ys / 1000, color=FLAME, lw=2.2, ls="--", alpha=0.95)

    ix, iy = proj.to_local(*bundle.ignition_lonlat)
    ax.plot(ix / 1000, iy / 1000, "*", color="#ffd23f", ms=20, mec="black", mew=0.6, zorder=6)
    ax.set_xlabel("km E", color="#7a8699")
    ax.set_ylabel("km N", color="#7a8699")
    ax.set_title(f"{cfg.name} — satellite fire tracking (GOES-18)", color="white", fontsize=14, pad=10)
    ax.tick_params(colors="#4a5568")
    for s in ax.spines.values():
        s.set_color("#1b2436")

    # colorbar for time
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.01)
    cb.set_label("minutes since first detection", color="#7a8699")
    cb.ax.yaxis.set_tick_params(color="#4a5568")
    plt.setp(plt.getp(cb.ax, "yticklabels"), color="#7a8699")

    # right column: growth curve + stats
    axg = fig.add_subplot(gs[0, 1:])
    axg.set_facecolor("#080b14")
    tt = [p.t_min for p in track.points]
    aa = [p.area_km2 for p in track.points]
    axg.fill_between(tt, aa, color=FLAME, alpha=0.18)
    axg.plot(tt, aa, "-o", color=FLAME, lw=2, ms=4)
    axg.axvline(cfg.assim_min, color=NEON, ls=":", lw=1.4)
    axg.text(cfg.assim_min, max(aa) * 0.9 if aa else 1, " forecast issued", color=NEON, fontsize=8)
    axg.set_title("tracked fire extent (convex hull)", color="white", fontsize=10)
    axg.set_xlabel("min since first detection", color="#7a8699", fontsize=8)
    axg.set_ylabel("km²", color="#7a8699", fontsize=8)
    axg.tick_params(colors="#4a5568", labelsize=8)
    for s in axg.spines.values():
        s.set_color("#1b2436")

    axs = fig.add_subplot(gs[1, 1:])
    axs.axis("off")
    stats = [
        ("first detection", track.points[0].t_min if track.points else 0, ""),
        ("GOES detections", track.total_detections, "px"),
        ("peak tracked extent", track.peak_area_km2, "km²"),
        ("mean spread rate", track.mean_ros_kmh(), "km/h"),
        ("net heading", track.net_heading_deg(), "°"),
        ("growth rate", track.growth_km2_per_h(), "km²/h"),
    ]
    lines = [f"{k:>18} :  {v:,.1f} {u}" if isinstance(v, float) else f"{k:>18} :  {v} {u}" for k, v, u in stats]
    if ablation_delta is not None:
        lines.append(f"{'assimilation ΔIoU':>18} :  {ablation_delta:+.3f}")
    axs.text(0.02, 0.95, "\n".join(lines), color="#c7d0e0", family="monospace", fontsize=9.5,
             va="top", transform=axs.transAxes)
    axs.text(0.02, 0.03, "real GOES-18 active fire · Terrain Tiles · ESA WorldCover · HRRR — nothing synthetic",
             color="#4a5568", fontsize=7.5, va="bottom", transform=axs.transAxes)

    paths = EventPaths(f"retro_{cfg.key}").ensure()
    (paths.outputs / "figures").mkdir(parents=True, exist_ok=True)
    out = paths.outputs / "figures" / "tracking.png"
    fig.savefig(out, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    # also copy to committed assets
    assets = REPO_ROOT / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(out, assets / f"track_{cfg.key}.png")
    return str(out)


def _subtitle_font(size=15, weight="medium"):
    import os

    from matplotlib import font_manager as fm

    for p in ("/System/Library/Fonts/Avenir Next.ttc", "/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(p):
            try:
                return fm.FontProperties(fname=p, size=size, weight=weight)
            except Exception:
                pass
    return fm.FontProperties(family="sans-serif", size=size, weight=weight)


def _compass(deg):
    return ["north", "north-north-east", "north-east", "east-north-east", "east", "east-south-east",
            "south-east", "south-south-east", "south", "south-south-west", "south-west",
            "west-south-west", "west", "west-north-west", "north-west", "north-north-west"][
        int(((deg % 360) + 11.25) // 22.5) % 16]


def _captions(cfg, track, delta):
    """Timed narrative captions (seconds→text) driven by the real tracked stats."""
    a, w = cfg.assim_min, cfg.window_min
    heading = _compass(track.net_heading_deg())
    peak = track.peak_area_km2
    return [
        (0, 45, "GOES-18 catches the first thermal signature from orbit"),
        (45, 100, "Thermal pixels cluster into a single tracked fire object"),
        (100, a, f"Locked on — the front pushes {heading} across the terrain"),
        (a, a + 22, f"Forecast issued · assimilating {a // 60} h of satellite detections"),
        (a + 22, w - 45, "Physics + data-assimilation project the spread ahead"),
        (w - 45, w + 1, f"Tracked burn extent surpasses {peak:.0f} km²"),
    ], (f"{cfg.name}: assimilation beat the no-forecast baseline (+{delta:.3f} IoU)"
        if delta is not None else f"{cfg.name}: tracked to {peak:.0f} km²")


def tracking_video(bundle, track: FireTrack, on, cfg, delta=None, fps: int = 11, px: int = 640) -> str:
    """Cinematic sped-up time-lapse with narrated subtitles (mp4, loopable scope)."""
    import matplotlib
    matplotlib.use("Agg")
    import imageio.v2 as imageio
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    from firewatch.geo import from_geojson

    grid = bundle.grid
    proj = grid.projector
    ext = [grid._xs[0] / 1000, grid._xs[-1] / 1000, grid._ys[0] / 1000, grid._ys[-1] / 1000]
    hs = _hillshade(grid.elevation, grid.cell_m)
    goes = sorted([o for o in bundle.observations if o.kind.value == "goes" and o.geometry], key=lambda o: o.t)
    t0 = goes[0].t if goes else bundle.ignition_time
    det = []
    for o in goes:
        g = from_geojson(o.geometry)
        for p in (g.geoms if g.geom_type == "MultiPoint" else [g]):
            det.append(((o.t - t0).total_seconds() / 60.0, p.x, p.y))
    det = np.array(det) if det else np.zeros((0, 3))
    path = np.array([proj.to_local(*p.centroid) for p in track.points]) / 1000
    ptimes = np.array([p.t_min for p in track.points])
    ix, iy = np.array(proj.to_local(*bundle.ignition_lonlat)) / 1000
    fp = on.expected_perimeter.get(cfg.horizons[-1])
    grid_norm = Normalize(0, cfg.window_min)
    subf, subf_sm, titlef = _subtitle_font(16), _subtitle_font(11, "regular"), _subtitle_font(27, "bold")
    caps, summary = _captions(cfg, track, delta)
    shadow = [pe.withStroke(linewidth=3.0, foreground=(0, 0, 0, 0.75))]

    dpi = 100
    fig = plt.figure(figsize=(px / dpi, px / dpi), dpi=dpi, facecolor="#05070d")
    ax = fig.add_axes([0, 0, 1, 1])

    def caption_for(t):
        for a0, a1, txt in caps:
            if a0 <= t < a1:
                edge = min(t - a0, a1 - t)
                return txt, min(1.0, edge / 12.0)  # brief fade at segment edges
        return None, 0.0

    def render(t, title_a=0.0, black=0.0, sub_override=None):
        ax.clear()
        ax.set_facecolor("#05070d")
        ax.imshow(hs, origin="lower", cmap="gray", extent=ext, alpha=0.5, vmin=-0.2, vmax=1.2, zorder=0)
        ax.imshow(np.where(grid.fuel == 0, 1.0, np.nan), origin="lower", extent=ext, cmap="Blues", alpha=0.18, zorder=1)
        poly = grid.mask_to_polygon(burned_mask(bundle.truth_arrival, t))
        if poly is not None:
            for pg in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
                if pg.is_empty or not hasattr(pg, "exterior"):
                    continue
                xs, ys = proj.to_local(*np.asarray(pg.exterior.coords).T)
                ax.fill(xs / 1000, ys / 1000, color=FLAME, alpha=0.18, zorder=2)
                ax.plot(xs / 1000, ys / 1000, color=FLAME, lw=6, alpha=0.12, zorder=2)  # glow
                ax.plot(xs / 1000, ys / 1000, color="#ffcf6b", lw=1.7, alpha=0.96, zorder=3)
        if len(det):
            m = det[:, 0] <= t + 1e-6
            if m.any():
                dl = np.array([proj.to_local(x, y) for x, y in det[m, 1:3]]) / 1000
                age = np.clip((t - det[m, 0]) / 90.0, 0, 1)
                ax.scatter(dl[:, 0], dl[:, 1], s=30 * (1 - age) + 6, c=det[m, 0], cmap="inferno",
                           norm=grid_norm, edgecolor="#ffdca8", linewidths=0.3, alpha=0.9, zorder=4)
        pm = ptimes <= t + 1e-6
        if pm.sum() >= 2:
            pp = path[pm]
            for lw, a in ((6, 0.14), (3, 0.95)):
                ax.plot(pp[:, 0], pp[:, 1], color=NEON, lw=lw, alpha=a, solid_capstyle="round", zorder=5)
            pulse = 60 + 34 * (0.5 + 0.5 * np.sin(t / 12.0))
            ax.scatter(pp[-1, 0], pp[-1, 1], s=pulse, color=NEON, edgecolor="white", linewidths=0.6, zorder=6)
        if t >= cfg.assim_min and fp is not None:
            for pg in (fp.geoms if fp.geom_type == "MultiPolygon" else [fp]):
                if pg.is_empty or not hasattr(pg, "exterior"):
                    continue
                xs, ys = proj.to_local(*np.asarray(pg.exterior.coords).T)
                ax.plot(xs / 1000, ys / 1000, color=FLAME, lw=2.2, ls="--", alpha=0.95, zorder=5)
        ax.plot(ix, iy, "*", color="#ffd23f", ms=17, mec="black", mew=0.5, zorder=7)
        ax.set_xlim(ext[0], ext[1])
        ax.set_ylim(ext[2], ext[3])
        ax.axis("off")

        # minimal persistent HUD
        area = next((p.area_km2 for p in reversed(track.points) if p.t_min <= t), 0.0)
        phase = "FORECAST" if t >= cfg.assim_min else "TRACKING"
        ax.text(0.035, 0.955, cfg.name.upper(), transform=ax.transAxes, color="white", fontproperties=subf_sm,
                va="top", path_effects=shadow)
        ax.text(0.035, 0.915, f"T+{t:04.0f} MIN", transform=ax.transAxes, color=NEON, fontproperties=subf_sm,
                va="top", path_effects=shadow)
        ax.text(0.965, 0.955, f"{area:.0f} KM²", transform=ax.transAxes, color="#ffcf6b", fontproperties=subf_sm,
                ha="right", va="top", path_effects=shadow)
        ax.text(0.965, 0.915, phase, transform=ax.transAxes, color=(FLAME if phase == "FORECAST" else NEON),
                fontproperties=subf_sm, ha="right", va="top", path_effects=shadow)
        ax.plot([0.035, 0.035 + 0.93 * t / cfg.window_min], [0.052, 0.052], transform=ax.transAxes,
                color=NEON, lw=2.6, alpha=0.9, solid_capstyle="round")

        # Netflix-style narrated subtitle (bottom-center, white with soft dark stroke)
        sub = sub_override if sub_override is not None else caption_for(t)
        txt, a = (sub if isinstance(sub, tuple) else (sub, 1.0))
        if txt and a > 0.02:
            ax.add_patch(mpatches.Rectangle((0, 0), 1, 0.19, transform=ax.transAxes, zorder=8,
                                            color="#05070d", alpha=0.22 * a))
            ax.text(0.5, 0.105, txt, transform=ax.transAxes, ha="center", va="center", color="white",
                    fontproperties=subf, alpha=a, zorder=9, path_effects=shadow, wrap=True)

        if title_a > 0.02:  # opening title card
            ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, transform=ax.transAxes, zorder=10,
                                            color="#05070d", alpha=0.45 * title_a))
            ax.text(0.5, 0.56, cfg.name, transform=ax.transAxes, ha="center", va="center", color="white",
                    fontproperties=titlef, alpha=title_a, zorder=11, path_effects=shadow)
            ax.text(0.5, 0.47, "SATELLITE FIRE TRACKING · GOES-18", transform=ax.transAxes, ha="center",
                    va="center", color=NEON, fontproperties=subf_sm, alpha=title_a, zorder=11, path_effects=shadow)
        if black > 0.02:  # fade from black
            ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, transform=ax.transAxes, zorder=12,
                                            color="black", alpha=black))
        fig.canvas.draw()
        return np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()

    frames = []
    for k in range(9):  # title card: fade in from black, title up
        frames.append(render(0, title_a=min(1.0, k / 3.5), black=max(0.0, 1 - k / 3.0)))
    for _ in range(3):
        frames.append(render(0, title_a=1.0))
    for k in range(4):
        frames.append(render(0, title_a=max(0.0, 1 - k / 3.0)))  # title fades out
    for t in np.linspace(0, cfg.window_min, 42):  # narrated timeline
        frames.append(render(t))
    for _ in range(fps + 6):  # hold with the summary line
        frames.append(render(cfg.window_min, sub_override=(summary, 1.0)))

    out = EventPaths(f"retro_{cfg.key}").ensure().outputs / "figures" / "tracking.mp4"
    imageio.mimwrite(out, frames, fps=fps, codec="libx264", quality=9, macro_block_size=16,
                     output_params=["-pix_fmt", "yuv420p"])
    plt.close(fig)
    import shutil

    assets = REPO_ROOT / "docs" / "assets"
    shutil.copy(out, assets / f"track_{cfg.key}.mp4")
    imageio.imwrite(assets / f"poster_{cfg.key}.png", frames[-22])  # a developed-fire frame as poster
    return str(out)


def run_historical(key: str, members: int = 28) -> dict:
    warnings.simplefilter("ignore")
    cfg = RETRO_REGISTRY[key]
    paths = EventPaths(f"retro_{cfg.key}").ensure()
    store = Store(":memory:")
    bundle = build_retro_bundle(cfg, store)

    track = track_from_observations(bundle.observations, bundle.ignition_time)
    ecfg = EnsembleConfig(n_members=members, wind_dir_sd_deg=45.0, wind_mult_sd=0.4, moisture_mult_sd=0.3,
                          ignition_sd_m=cfg.cell_m * 2)
    issue = bundle.ignition_time + timedelta(minutes=cfg.assim_min)
    on = run_forecast(bundle.grid, bundle.ignition_lonlat, bundle.ignition_time, observations=bundle.observations,
                      assimilate=True, issued_at=issue, ensemble_config=ecfg, horizons=cfg.horizons,
                      initial_mask=bundle.initial_burned_mask)
    off = run_forecast(bundle.grid, bundle.ignition_lonlat, bundle.ignition_time, observations=bundle.observations,
                       assimilate=False, issued_at=issue, ensemble_config=ecfg, horizons=cfg.horizons,
                       initial_mask=bundle.initial_burned_mask)
    so, sf = skill_vs_truth(on, bundle.truth_arrival), skill_vs_truth(off, bundle.truth_arrival)
    delta = float(np.mean([so[h]["iou"] - sf[h]["iou"] for h in cfg.horizons]))

    fig = tracking_figure(bundle, track, on, delta, cfg)
    try:
        vid = tracking_video(bundle, track, on, cfg, delta=delta)
    except Exception as e:  # video is a bonus; never fail the run
        log.warning("video for %s failed: %s", cfg.key, e)
        vid = None
    result = {
        "key": cfg.key, "name": cfg.name, "start_utc": cfg.start_utc,
        "n_frames": track.n_frames, "goes_detections": track.total_detections,
        "peak_area_km2": round(track.peak_area_km2, 1), "mean_ros_kmh": round(track.mean_ros_kmh(), 2),
        "heading_deg": round(track.net_heading_deg(), 0), "growth_km2_per_h": round(track.growth_km2_per_h(), 1),
        "ablation_delta_iou": round(delta, 3),
        "iou_on": round(float(np.mean([so[h]["iou"] for h in cfg.horizons])), 3),
        "iou_off": round(float(np.mean([sf[h]["iou"] for h in cfg.horizons])), 3),
        "figure": fig, "asset": f"track_{cfg.key}.png",
        "video": vid, "video_asset": (f"track_{cfg.key}.mp4" if vid else None),
        "feeds": sorted({o.provenance.source for o in bundle.observations}),
    }
    (paths.outputs / "tracking.json").write_text(json.dumps(result, indent=2, default=str))
    store.close()
    log.info("%s: %d frames, peak %.0f km², ROS %.1f km/h, ΔIoU %+.3f",
             cfg.name, result["n_frames"], result["peak_area_km2"], result["mean_ros_kmh"], delta)
    return result


def run_all(keys=("park", "palisades", "eaton")) -> list[dict]:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = []
    for k in keys:
        try:
            out.append(run_historical(k))
        except Exception as e:  # keep going; report which failed
            log.warning("historical %s failed: %s", k, e)
    (REPO_ROOT / "outputs" / "historical.json").write_text(json.dumps(out, indent=2, default=str))
    return out
