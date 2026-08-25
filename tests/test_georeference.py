"""Novelty 1: DEM ray-cast accuracy, skyline tilt self-cal, and triangulation (FR-GEO-1..4)."""
import math

import numpy as np

from firewatch.geo import haversine_m
from firewatch.ontology.objects import Camera, new_id
from firewatch.perception import skyline, triangulate
from firewatch.perception.georeference import georeference_pixel
from firewatch.terrain import DEM


def _valley_dem():
    n, cell = 240, 100
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    elev = 600 - 0.03 * cell * np.hypot(xs - n * 0.2, ys - n * 0.2) + 40 * np.sin(xs / n * 3)
    return DEM(38.5, -122.6, cell, elev)


def _aim(dem, cam_lonlat, tgt_local):
    cx, cy = dem.lonlat_to_local(*cam_lonlat)
    cam_elev = dem.sample_local(cx, cy) + 20
    tx, ty = tgt_local
    R = math.hypot(tx - cx, ty - cy)
    az = math.degrees(math.atan2(tx - cx, ty - cy)) % 360
    el = math.degrees(math.atan2(dem.sample_local(tx, ty) - cam_elev, R))
    return cam_elev, az, el


def test_ray_cast_clear_los_accurate():
    dem = _valley_dem()
    cam_ll = (-122.66, 38.44)
    cx, cy = dem.lonlat_to_local(*cam_ll)
    tgt = (cx + 2100, cy + 2100)
    cam_elev, az, el = _aim(dem, cam_ll, tgt)
    cam = Camera(id=new_id("c"), name="c", lat=cam_ll[1], lon=cam_ll[0], elev_m=cam_elev, pan_deg=az, tilt_deg=el, fov_deg=50)
    ll = georeference_pixel(cam, cam.image_width / 2, cam.image_height / 2, dem)
    tgt_lonlat = dem.local_to_lonlat(*tgt)
    assert haversine_m(ll[0], ll[1], *tgt_lonlat) < dem.cell_m  # sub-cell accuracy on clear LOS


def test_skyline_selfcal_recovers_tilt():
    dem = _valley_dem()
    cam_ll = (-122.66, 38.44)
    cx, cy = dem.lonlat_to_local(*cam_ll)
    tgt = (cx + 2100, cy + 2100)
    cam_elev, az, el = _aim(dem, cam_ll, tgt)
    cam = Camera(id=new_id("c"), name="c", lat=cam_ll[1], lon=cam_ll[0], elev_m=cam_elev, pan_deg=az, tilt_deg=el, fov_deg=50)
    cols = np.linspace(150, 1770, 40).astype(int)
    ela = skyline.horizon_elevation_angles(cam, dem, cols)
    observed = skyline.elevation_angles_to_rows(cam, ela, el)  # synthetic 'imaged' skyline at true tilt
    cam_wrong = cam.model_copy()
    cam_wrong.tilt_deg = el - 1.5
    cal = skyline.calibrate_tilt(cam_wrong, dem, observed, cols, tilt_search=(el - 6, el + 6), tilt_step=0.1)
    assert abs(cal.tilt_deg - el) < 0.3  # recovers the true tilt


def test_triangulation_accurate():
    from firewatch.geo import bearing_deg

    tgt = (-122.60, 38.50)
    cams = [(-122.66, 38.47), (-122.55, 38.46)]
    obs = [(la, lo, bearing_deg(lo, la, *tgt)) for lo, la in cams]
    tri = triangulate.triangulate_bearings(obs)
    assert haversine_m(tri.lon, tri.lat, *tgt) < 100  # two cameras -> tight fix
