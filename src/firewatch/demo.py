"""Fully-offline synthetic demo event (no network / no keys) — the `make demo` path.

Builds a self-contained fire with terrain, cameras, evacuation zones, egress roads, structures, and
a synthetic 'truth' fire from which we sample GOES/VIIRS hotspots, a camera-derived front (via the
real detect→segment→georeference pipeline on a rendered frame), and an official perimeter. Every
synthetic artifact is labeled as such (CLAUDE.md principle 2). This exercises the entire M1→M5 stack
end-to-end so the pipeline, decisions, calibration, and COP JSON are all reproducible offline.
"""
from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from firewatch.forecast.engine import truth_arrival
from firewatch.forecast.grid import synthetic_grid
from firewatch.forecast.spread import SpreadParams, burned_mask
from firewatch.geo import destination_point
from firewatch.ontology.objects import (
    Camera,
    Fire,
    FirePerimeter,
    FireStatus,
    Observation,
    ObservationKind,
    PerimeterSource,
    PopulationZone,
    Provenance,
    RoadSegment,
    Structure,
    WeatherCell,
    new_id,
)
from firewatch.ontology.store import Store
from firewatch.pipeline import EventBundle
from firewatch.terrain import DEM

IGNITION = (-122.60, 38.50)
IGN_TIME = datetime(2025, 8, 20, 18, 0, tzinfo=UTC)
WIND_SPEED = 7.0
WIND_DIR_TO = 62.0  # blowing toward ENE
SYN = "synthetic-truth (labeled: not a real fire)"


def _rect_zone(center_lonlat, half_m=500.0):
    lon, lat = center_lonlat
    pts = [
        destination_point(lon, lat, 45, half_m * 1.414),
        destination_point(lon, lat, 135, half_m * 1.414),
        destination_point(lon, lat, 225, half_m * 1.414),
        destination_point(lon, lat, 315, half_m * 1.414),
    ]
    return Polygon(pts)


def build_demo_event(store: Store, event_id: str = "demo", n: int = 110, cell_m: float = 200.0) -> EventBundle:
    grid = synthetic_grid(38.50, -122.60, cell_m=cell_m, n=n, wind_speed_ms=WIND_SPEED, wind_dir_to_deg=WIND_DIR_TO)
    dem = DEM.from_grid(grid)

    fire = Fire(
        id="fire_demo", t=IGN_TIME, name="Ridge Demo Fire", discovered_at=IGN_TIME,
        status=FireStatus.active, centroid={"type": "Point", "coordinates": list(IGNITION)},
        ignition_estimate={"type": "Point", "coordinates": list(IGNITION)},
    )

    # the 'truth' fire (stronger, right-drifting wind) — the reference the forecast is scored against
    truth = truth_arrival(grid, IGNITION, SpreadParams(wind_mult=1.3, wind_dir_offset_deg=12, ros_mult=1.15))

    # cameras positioned to view the fire from two directions (poses aimed at ignition)
    cams = []
    for name, (clon, clat, _brg_from) in {
        "Ridge-W": (-122.66, 38.48, 55.0),
        "Ridge-S": (-122.585, 38.455, 340.0),
    }.items():
        cx, cy = dem.lonlat_to_local(clon, clat)
        elev = dem.sample_local(cx, cy) + 25
        # pan toward ignition
        ix, iy = dem.lonlat_to_local(*IGNITION)
        import math
        pan = math.degrees(math.atan2(ix - cx, iy - cy)) % 360
        R = math.hypot(ix - cx, iy - cy)
        tilt = math.degrees(math.atan2(dem.sample_local(ix, iy) - elev, R))
        cams.append(Camera(id=new_id("cam"), t=IGN_TIME, name=name, lat=clat, lon=clon, elev_m=elev,
                           pan_deg=pan, tilt_deg=tilt, fov_deg=55, image_width=1280, image_height=720,
                           network="ALERTCalifornia (synthetic)", pan_uncertainty_deg=2.0, tilt_uncertainty_deg=3.0))

    # evacuation zones downwind (ENE), where the fire is heading — placed so the fire reaches them
    # tens of minutes to a couple hours out, giving meaningful (positive) warning lead-times.
    zones = []
    for i, (name, pop, dist, brg, half) in enumerate([
        ("Oakridge", 900, 2300, 58, 480),
        ("Canyon Vista", 1800, 3700, 62, 620),
        ("Mill Creek", 400, 5200, 74, 520),
    ]):
        c = destination_point(*IGNITION, brg, dist)
        zones.append(PopulationZone(id=f"zone_{i}", t=IGN_TIME, name=name, geometry=_rect_zone(c, half), population=pop))

    # egress roads (lines) leaving the zones
    roads = []
    a = destination_point(*IGNITION, 60, 3000)  # near the Canyon Vista / Oakridge corridor
    roads.append(RoadSegment(id="road_0", t=IGN_TIME, name="Canyon Rd (egress E)",
                             geometry=LineString([a, destination_point(*a, 80, 5000)]), highway="secondary"))
    roads.append(RoadSegment(id="road_1", t=IGN_TIME, name="Ridge Rd (egress N)",
                             geometry=LineString([a, destination_point(*a, 350, 4000)]), highway="residential"))

    # structures clustered in the nearest zone
    rng = np.random.default_rng(5)
    structures = []
    zc = zones[1].geom().centroid
    for k in range(40):
        dlon = rng.normal(0, 0.004)
        dlat = rng.normal(0, 0.003)
        structures.append(Structure(id=f"bldg_{k}", t=IGN_TIME,
                                     footprint=Point(zc.x + dlon, zc.y + dlat).buffer(0.0003),
                                     type="residential", population_est=2.6))

    weather = WeatherCell(id="wx_0", t=IGN_TIME, bbox=list(grid_bbox(grid)),
                          wind_u=WIND_SPEED * np.sin(np.radians(WIND_DIR_TO)),
                          wind_v=WIND_SPEED * np.cos(np.radians(WIND_DIR_TO)), rh=18, temp_c=33, source="HRRR (synthetic)")

    # observations sampled from truth (labeled synthetic) at increasing times
    observations = []
    obs_perims = []
    for mm in (20, 40, 60, 90):
        t = IGN_TIME + timedelta(minutes=mm)
        mask = burned_mask(truth, mm)
        # VIIRS/GOES hotspots
        ii, jj = np.nonzero(mask)
        if len(ii):
            kind = ObservationKind.viirs if mm % 40 == 0 else ObservationKind.goes
            sigma = 375 if kind == ObservationKind.viirs else 1800
            sel = rng.choice(len(ii), size=min(35, len(ii)), replace=False)
            from shapely.geometry import MultiPoint
            pts = MultiPoint([Point(*grid.cell_to_lonlat(int(ii[k]), int(jj[k]))) for k in sel])
            observations.append(Observation(id=new_id("obs"), t=t, fire_id=fire.id, kind=kind, geometry=pts,
                                            provenance=Provenance(source=SYN, product=kind.value.upper(),
                                                                  reported_uncertainty_m=sigma), reported_uncertainty_m=sigma))
        # observed perimeter (also the map "observed" layer + scrubber)
        poly = grid.mask_to_polygon(mask)
        if poly is not None:
            obs_perims.append(FirePerimeter(id=new_id("perim"), t=t, fire_id=fire.id, geometry=poly,
                                            source=PerimeterSource.observed, confidence=1.0))

    # one official IR perimeter + a camera-derived front (real detect->segment->georeference) at 60 min
    t60 = IGN_TIME + timedelta(minutes=60)
    poly60 = grid.mask_to_polygon(burned_mask(truth, 60))
    if poly60 is not None:
        observations.append(Observation(id=new_id("obs"), t=t60, fire_id=fire.id,
                                        kind=ObservationKind.official_perimeter, geometry=poly60,
                                        provenance=Provenance(source="NIFC (synthetic)", product="IR perimeter",
                                                              reported_uncertainty_m=120), reported_uncertainty_m=120))
    cam_obs = _camera_front_observation(cams[0], dem, grid, truth, 60, fire.id, t60)
    if cam_obs is not None:
        observations.append(cam_obs)

    # render camera frames (with detector box + plume mask overlay) for the Observe pane
    _save_camera_frames(event_id, cams, dem, grid, truth, minutes=60)

    # persist base ontology objects
    store.put(fire)
    store.put_many(cams + zones + roads + structures + [weather] + obs_perims + observations)

    bundle = EventBundle(
        event_id=event_id, store=store, grid=grid, dem=dem, fire=fire,
        ignition_lonlat=IGNITION, ignition_time=IGN_TIME, zones=zones, roads=roads,
        structures=structures, cameras=cams, observations=observations,
        wind={"speed_ms": WIND_SPEED, "dir_to_deg": WIND_DIR_TO, "rh_pct": 18, "temp_c": 33, "source": weather.source},
        truth_arrival=truth,
        note="Synthetic offline demo — terrain, fuels, wind, and 'truth' fire are simulated and labeled as such. "
             "Not a real fire; for real events use `make replay FIRE=<id>`.",
    )
    return bundle


def grid_bbox(grid):
    corners = [grid.cell_to_lonlat(i, j) for i in (0, grid.ny - 1) for j in (0, grid.nx - 1)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return (min(lons), min(lats), max(lons), max(lats))


def render_camera_frame(camera: Camera, dem: DEM, grid, truth, minutes: int) -> np.ndarray:
    """Render a plausible tower-cam frame: sky, terrain below the DEM skyline, and a smoke plume at
    the projected fire front. Used to drive the real detect→segment→georeference pipeline in the demo."""
    import math
    W, H = camera.image_width, camera.image_height
    img = np.zeros((H, W, 3), dtype=np.uint8)
    cols = np.arange(0, W, 4)
    from firewatch.perception.skyline import elevation_angles_to_rows, horizon_elevation_angles
    el = horizon_elevation_angles(camera, dem, cols, max_range_m=30000, step_m=dem.cell_m * 2)
    rows = elevation_angles_to_rows(camera, el, camera.tilt_deg)
    horizon = np.interp(np.arange(W), cols, rows).clip(0, H - 1)
    yy = np.arange(H)[:, None].astype(float)
    sky = yy < horizon[None, :]
    # sky: blue gradient (lighter toward the horizon); ground: green→brown by row (haze near horizon)
    depth = np.clip(yy / H, 0, 1)
    img[..., 0] = np.where(sky, 175 + 55 * depth, 70 + 25 * depth)   # B
    img[..., 1] = np.where(sky, 140 + 55 * depth, 105 - 25 * depth)  # G
    img[..., 2] = np.where(sky, 95 + 60 * depth, 80 - 20 * depth)    # R
    img = img.clip(0, 255).astype(np.uint8)

    # project the fire front centroid into the image and draw a billowing smoke plume above it
    ii, jj = np.nonzero(burned_mask(truth, minutes))
    if len(ii):
        clon, clat = grid.cell_to_lonlat(int(np.median(ii)), int(np.median(jj)))
        cx, cy = dem.lonlat_to_local(camera.lon, camera.lat)
        fx, fy = dem.lonlat_to_local(clon, clat)
        R = math.hypot(fx - cx, fy - cy)
        az = math.degrees(math.atan2(fx - cx, fy - cy))
        elev = math.degrees(math.atan2(dem.sample_local(fx, fy) - camera.elev_m, R))
        f = (W / 2) / math.tan(math.radians(camera.fov_deg) / 2)
        px = W / 2 + f * math.tan(math.radians(az - camera.pan_deg))
        py = H / 2 + f * math.tan(math.radians(camera.tilt_deg - elev))
        if 0 <= px < W:
            rng = np.random.default_rng(minutes)
            XX, YY = np.meshgrid(np.arange(W).astype(float), np.arange(H).astype(float))
            top = py - 230
            hnorm = np.clip((py - YY) / (py - top), 0, 1)  # 0 at base, 1 at top
            axis = px + 55 * hnorm**1.4 + 14 * np.sin(YY / 26.0)  # lean + billow with height
            width = 16 + 78 * hnorm + 10 * np.sin(YY / 15.0 + 1)  # narrow base -> wide top
            r = np.abs(XX - axis) / np.maximum(width, 1)
            softness = np.clip(1.0 - r, 0, 1) * (YY < py) * (YY > top)
            softness *= (0.75 + 0.25 * rng.random(img.shape[:2]))  # texture
            gray = np.full(img.shape[:2], 200.0)
            alpha = np.clip(softness * 1.4, 0, 0.92)[..., None]
            img = (img * (1 - alpha) + gray[..., None] * alpha).clip(0, 255).astype(np.uint8)
    return img


def _save_camera_frames(event_id, cams, dem, grid, truth, minutes=60):
    """Render each camera frame, overlay the detector box + plume mask, and save for the Observe pane."""
    from firewatch.config import EventPaths
    from firewatch.perception.detect import SmokeDetector
    from firewatch.perception.features import smoke_state
    from firewatch.perception.segment import PlumeSegmenter

    try:
        import cv2
    except Exception:
        return
    outdir = EventPaths(event_id).ensure().outputs / "frames"
    outdir.mkdir(parents=True, exist_ok=True)
    det = SmokeDetector()
    seg = PlumeSegmenter()
    for cam in cams:
        try:
            frame = render_camera_frame(cam, dem, grid, truth, minutes)
            dets = det.detect(frame, thresh=0.4)
            smoke = [d for d in dets if d.label == "smoke"]
            overlay = frame.copy()
            state = None
            if smoke:
                d = smoke[0]
                mask = seg.segment(frame, d.bbox)
                if mask.any():
                    tint = overlay.copy()
                    tint[mask] = (60, 130, 245)  # BGR orange tint on the plume
                    overlay = cv2.addWeighted(tint, 0.35, overlay, 0.65, 0)
                    state = smoke_state(mask, cam)
                cv2.rectangle(overlay, (d.bbox[0], d.bbox[1]), (d.bbox[2], d.bbox[3]), (60, 200, 255), 2)
                label = f"smoke {d.score:.2f} [{d.backend}]"
                cv2.putText(overlay, label, (d.bbox[0], max(0, d.bbox[1] - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 200, 255), 2)
            if state is not None:
                cv2.putText(overlay, f"area {state.area_px}px  bearing {state.bearing_deg:.0f}  tilt {state.plume_tilt_deg:.0f}",
                            (12, frame.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cam.last_frame = f"frames/{cam.id}.png"
            cv2.imwrite(str(outdir / f"{cam.id}.png"), overlay)
        except Exception:
            continue


def _camera_front_observation(camera, dem, grid, truth, minutes, fire_id, t):
    """Run the real perception pipeline on a rendered frame to produce a camera_front Observation."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            from firewatch.perception.detect import SmokeDetector
            from firewatch.perception.georeference import georeference_to_observation
            from firewatch.perception.segment import PlumeSegmenter
            frame = render_camera_frame(camera, dem, grid, truth, minutes)
            dets = SmokeDetector().detect(frame, thresh=0.4)
            smoke = [d for d in dets if d.label == "smoke"]
            if not smoke:
                return None
            mask = PlumeSegmenter().segment(frame, smoke[0].bbox)
            if not mask.any():
                return None
            return georeference_to_observation(camera, mask, dem, fire_id, t=t, n_samples=30, max_range_m=30000)
        except Exception:
            return None
