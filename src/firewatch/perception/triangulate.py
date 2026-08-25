"""Multi-camera triangulation (FR-GEO-4).

When two or more cameras see the same plume, the intersection of their bearing lines fixes the fire
far more tightly than a single camera's ray-cast (which is sensitive to tilt and plume-base
ambiguity). We solve the least-squares intersection of the bearing lines in a local meter frame and
report an uncertainty ellipse from the geometry + residuals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from firewatch.geo import Projector
from firewatch.ontology.objects import Camera


def bearing_to_plume(camera: Camera, mask: np.ndarray) -> float:
    """Central azimuth (deg, 0=N clockwise) from a camera to the plume centroid in its image."""
    f = (camera.image_width / 2.0) / math.tan(math.radians(camera.fov_deg) / 2.0)
    cols = np.where(mask.any(axis=0))[0]
    cx = float(cols.mean()) if len(cols) else camera.image_width / 2.0
    dx = cx - camera.image_width / 2.0
    return (camera.pan_deg + math.degrees(math.atan2(dx, f))) % 360.0


@dataclass
class Triangulation:
    lon: float
    lat: float
    semi_major_m: float
    semi_minor_m: float
    orientation_deg: float
    n_cameras: int
    residual_m: float


def triangulate_bearings(observations: list[tuple[float, float, float]]) -> Triangulation | None:
    """Least-squares intersection of bearing lines.

    `observations` = list of (lat, lon, bearing_deg). Returns the intersection point + an uncertainty
    ellipse, or None if fewer than 2 non-parallel bearings are given.
    """
    if len(observations) < 2:
        return None
    lat0 = float(np.mean([o[0] for o in observations]))
    lon0 = float(np.mean([o[1] for o in observations]))
    proj = Projector(lat0, lon0)

    A = np.zeros((2, 2))
    b = np.zeros(2)
    pts = []
    dirs = []
    for lat, lon, brg in observations:
        x, y = proj.to_local(lon, lat)
        p = np.array([x, y])
        az = math.radians(brg)
        d = np.array([math.sin(az), math.cos(az)])  # (east, north)
        M = np.eye(2) - np.outer(d, d)  # projector onto perpendicular of the bearing
        A += M
        b += M @ p
        pts.append(p)
        dirs.append(d)
    try:
        x = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None

    # residual: perpendicular distance from solution to each bearing line
    resid = []
    for p, d in zip(pts, dirs, strict=False):
        M = np.eye(2) - np.outer(d, d)
        resid.append(math.sqrt(float((x - p) @ M @ (x - p))))
    residual_m = float(np.mean(resid))

    # covariance ~ (A)^-1 scaled by residual variance -> ellipse
    cov = np.linalg.inv(A) * max(residual_m, 1.0) ** 2
    evals, evecs = np.linalg.eigh(cov)
    evals = np.clip(evals, 1e-6, None)
    order = np.argsort(evals)[::-1]
    semi = np.sqrt(evals[order]) * 2.0  # ~1-sigma scaled up to a usable envelope
    major_vec = evecs[:, order[0]]
    orientation = math.degrees(math.atan2(major_vec[0], major_vec[1])) % 180.0

    lon, lat = proj.to_wgs84(float(x[0]), float(x[1]))
    return Triangulation(
        lon=float(lon),
        lat=float(lat),
        semi_major_m=float(semi[0]),
        semi_minor_m=float(semi[1]),
        orientation_deg=float(orientation),
        n_cameras=len(observations),
        residual_m=residual_m,
    )


def triangulate_cameras(pairs: list[tuple[Camera, np.ndarray]]) -> Triangulation | None:
    """Convenience: triangulate from (camera, mask) pairs by taking each camera's plume bearing."""
    obs = [(cam.lat, cam.lon, bearing_to_plume(cam, mask)) for cam, mask in pairs]
    return triangulate_bearings(obs)
