"""Skyline-to-DEM tilt self-calibration (FR-GEO-3).

Tower-camera PTZ tilt metadata is often approximate. We refine it by matching the imaged horizon to
the DEM-rendered horizon: for each image column, the terrain's *maximum elevation angle* along that
column's azimuth (independent of tilt) fixes where the skyline should appear; the observed skyline
row then pins the tilt (and, optionally, a small pan correction). This is the step beyond Pyronear's
manual click and beyond assuming the reported pose is exact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from firewatch.ontology.objects import Camera
from firewatch.terrain import DEM


def horizon_elevation_angles(
    camera: Camera,
    dem: DEM,
    columns: np.ndarray,
    max_range_m: float = 30000.0,
    step_m: float | None = None,
) -> np.ndarray:
    """Max terrain elevation angle (degrees) along each column's azimuth — independent of tilt."""
    f = (camera.image_width / 2.0) / math.tan(math.radians(camera.fov_deg) / 2.0)
    cx, cy = dem.lonlat_to_local(camera.lon, camera.lat)
    step = step_m or max(dem.cell_m, 20.0)
    ranges = np.arange(step, max_range_m, step)
    out = np.full(len(columns), -90.0)
    for k, c in enumerate(columns):
        dx = c - camera.image_width / 2.0
        az = math.radians(camera.pan_deg + math.degrees(math.atan2(dx, f)))
        de, dn = math.sin(az), math.cos(az)
        xs = cx + de * ranges
        ys = cy + dn * ranges
        terr = np.array([dem.sample_local(x, y) for x, y in zip(xs, ys, strict=False)])
        el = np.degrees(np.arctan2(terr - camera.elev_m, ranges))
        out[k] = float(el.max())
    return out


def elevation_angles_to_rows(camera: Camera, el_angles: np.ndarray, tilt_deg: float) -> np.ndarray:
    """Convert horizon elevation angles to image rows for a candidate tilt."""
    f = (camera.image_width / 2.0) / math.tan(math.radians(camera.fov_deg) / 2.0)
    v_ang = np.radians(tilt_deg - el_angles)  # el = tilt - v_ang
    return camera.image_height / 2.0 + f * np.tan(v_ang)


def detect_skyline(image_gray: np.ndarray, columns: np.ndarray | None = None) -> np.ndarray:
    """Per-column skyline row from a grayscale image (strongest vertical brightness drop).

    Sky is bright/uniform above, terrain darker below; the boundary is the largest downward gradient
    in the upper part of the column. Returns NaN where no clear edge is found.
    """
    h, w = image_gray.shape
    cols = np.arange(w) if columns is None else columns
    grad = np.diff(image_gray.astype(float), axis=0)  # (h-1, w); negative = brightness drop
    rows = np.full(len(cols), np.nan)
    for k, c in enumerate(cols):
        g = -grad[:, c]  # positive where brightness drops
        r = int(np.argmax(g))
        if g[r] > 8:  # minimum contrast to count as a skyline edge
            rows[k] = r
    return rows


@dataclass
class TiltCalibration:
    tilt_deg: float
    pan_offset_deg: float
    rms_row_error: float
    n_columns: int


def calibrate_tilt(
    camera: Camera,
    dem: DEM,
    observed_rows: np.ndarray,
    columns: np.ndarray,
    tilt_search=(-15.0, 15.0),
    tilt_step: float = 0.25,
    refine_pan: bool = False,
    pan_search=(-6.0, 6.0),
    pan_step: float = 1.0,
) -> TiltCalibration:
    """Search tilt (and optionally a small pan offset) to best match the observed skyline.

    `observed_rows[k]` is the imaged skyline row for `columns[k]` (NaN allowed). Returns the refined
    tilt + residual RMS row error.
    """
    valid = ~np.isnan(observed_rows)
    obs = observed_rows[valid]
    cols = columns[valid]
    if len(obs) < 3:
        return TiltCalibration(camera.tilt_deg, 0.0, float("nan"), 0)

    pan_offsets = [0.0]
    if refine_pan:
        pan_offsets = list(np.arange(pan_search[0], pan_search[1] + 1e-9, pan_step))

    best = TiltCalibration(camera.tilt_deg, 0.0, float("inf"), len(obs))
    tilts = np.arange(tilt_search[0], tilt_search[1] + 1e-9, tilt_step)
    for pan_off in pan_offsets:
        cam = camera.model_copy()
        cam.pan_deg = camera.pan_deg + pan_off
        el = horizon_elevation_angles(cam, dem, cols)
        for tilt in tilts:
            pred = elevation_angles_to_rows(cam, el, float(tilt))
            rms = float(np.sqrt(np.mean((pred - obs) ** 2)))
            if rms < best.rms_row_error:
                best = TiltCalibration(float(tilt), float(pan_off), rms, len(obs))
    return best


def apply_calibration(camera: Camera, cal: TiltCalibration) -> Camera:
    cam = camera.model_copy()
    cam.tilt_deg = cal.tilt_deg
    cam.pan_deg = camera.pan_deg + cal.pan_offset_deg
    cam.tilt_uncertainty_deg = min(camera.tilt_uncertainty_deg, 1.0)  # self-cal tightens it
    return cam
