"""Front propagation via Minimum-Travel-Time (MTT) over the fire grid (FR-FC-1).

Each cell gets a head-fire ROS, head direction, and an elliptical shape (from `rothermel.py`).
We then solve for the fire's *arrival time* at every cell with a multi-source Dijkstra: the cost of
spreading from cell A to neighbor B is distance / ROS_A(in the A→B direction), where the directional
ROS follows the Rothermel ellipse. This is the same minimum-travel-time idea FlamMap uses; it is
deterministic, handles heterogeneous fuel/wind/slope and non-burnable barriers, and yields every
horizon (+15/+30/+60/+180 min) from a single solve.

The vectorized Rothermel here mirrors the scalar reference in `rothermel.py` (a test checks they
agree), so the physical prior stays debuggable.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np

from firewatch.forecast.grid import FireGrid
from firewatch.forecast.rothermel import (
    _HEAT,
    _MIDFLAME_FACTOR,
    _RHO_P,
    _SE,
    _ST,
    FTMIN_PER_MS,
    FUEL_MODELS,
    MPH_PER_MS,
    MS_PER_FTMIN,
)

# 8-neighbour offsets (di, dj) and their base distances in cell units
_NEIGHBORS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


@dataclass
class SpreadParams:
    """Per-member perturbations for the ensemble (FR-FC-2) + regularization (FR-FC-3)."""

    wind_mult: float = 1.0
    wind_dir_offset_deg: float = 0.0
    moisture_mult: float = 1.0
    ros_mult: float = 1.0
    ignition_offset_m: tuple[float, float] = (0.0, 0.0)  # (east, north) meters
    spread_cap_ms: float = 3.0  # cap head ROS (spurious-fire regularization)
    midflame_factor: float = _MIDFLAME_FACTOR


def _fuel_param_arrays(fuel: np.ndarray) -> dict[str, np.ndarray]:
    """Map fuel-model codes to per-cell parameter arrays (load, depth, sav, mx, burnable)."""
    maxc = max(FUEL_MODELS) + 1
    load = np.zeros(maxc)
    depth = np.ones(maxc)
    sav = np.full(maxc, 1500.0)
    mx = np.full(maxc, 0.2)
    burn = np.zeros(maxc)
    for c, fm in FUEL_MODELS.items():
        load[c], depth[c], sav[c], mx[c] = fm.load_dead_1h, fm.depth_ft, fm.sav, fm.mx_dead
        burn[c] = 1.0 if fm.burnable and fm.load_dead_1h > 0 else 0.0
    fc = np.clip(fuel, 0, maxc - 1)
    return {
        "load": load[fc],
        "depth": depth[fc],
        "sav": sav[fc],
        "mx": mx[fc],
        "burnable": burn[fc].astype(bool),
    }


def precompute_ros(grid: FireGrid, params: SpreadParams) -> dict[str, np.ndarray]:
    """Vectorized Rothermel over the whole grid -> R_head (m/s), head unit vector, eccentricity."""
    p = _fuel_param_arrays(grid.fuel)
    load, depth, sav, mx = p["load"], p["depth"], p["sav"], p["mx"]
    burnable = p["burnable"]

    # wind vector (scaled + rotated per member)
    ang = np.radians(params.wind_dir_offset_deg)
    ca, sa = np.cos(ang), np.sin(ang)
    u = (grid.wind_u * ca - grid.wind_v * sa) * params.wind_mult
    v = (grid.wind_u * sa + grid.wind_v * ca) * params.wind_mult
    wind_speed = np.hypot(u, v)

    # uphill gradient -> slope fraction and unit upslope direction
    gx, gy = grid.slope_gradient()
    smag = np.hypot(gx, gy)

    mf = np.clip(grid.moisture * params.moisture_mult, 0.005, 0.6)

    with np.errstate(divide="ignore", invalid="ignore"):
        rho_b = load / depth
        beta = rho_b / _RHO_P
        beta_op = 3.348 * sav**-0.8189
        beta_ratio = np.where(beta_op > 0, beta / beta_op, 0.0)
        gamma_max = sav**1.5 / (495.0 + 0.0594 * sav**1.5)
        a = 133.0 * sav**-0.7913
        gamma = gamma_max * beta_ratio**a * np.exp(a * (1.0 - beta_ratio))
        wn = load / (1.0 + _ST)
        rm = np.minimum(mf / mx, 1.0)
        eta_m = np.clip(1.0 - 2.59 * rm + 5.11 * rm**2 - 3.52 * rm**3, 0.0, 1.0)
        eta_s = min(1.0, 0.174 * _SE**-0.19)
        i_r = gamma * wn * _HEAT * eta_m * eta_s
        xi = np.exp((0.792 + 0.681 * sav**0.5) * (beta + 0.1)) / (192.0 + 0.2595 * sav)
        epsilon = np.exp(-138.0 / sav)
        q_ig = 250.0 + 1116.0 * mf
        heat_sink = rho_b * epsilon * q_ig
        ros_base_ftmin = np.where(heat_sink > 0, i_r * xi / heat_sink, 0.0)

        # wind & slope coefficients
        u_ftmin = np.maximum(0.0, wind_speed) * params.midflame_factor * FTMIN_PER_MS
        c = 7.47 * np.exp(-0.133 * sav**0.55)
        b = 0.02526 * sav**0.54
        e = 0.715 * np.exp(-3.59e-4 * sav)
        phi_w = np.where(u_ftmin > 0, c * (u_ftmin**b) * beta_ratio**-e, 0.0)
        phi_s = 5.275 * np.where(beta > 0, beta**-0.3, 0.0) * np.maximum(0.0, smag) ** 2

    ros_base_ms = np.nan_to_num(ros_base_ftmin * MS_PER_FTMIN)

    # combine wind & slope as vectors -> head direction + effective coefficient
    wu = np.divide(u, wind_speed, out=np.zeros_like(u), where=wind_speed > 0)
    wv = np.divide(v, wind_speed, out=np.zeros_like(v), where=wind_speed > 0)
    su = np.divide(gx, smag, out=np.zeros_like(gx), where=smag > 0)
    sv = np.divide(gy, smag, out=np.zeros_like(gy), where=smag > 0)
    phix = phi_w * wu + phi_s * su
    phiy = phi_w * wv + phi_s * sv
    phimag = np.hypot(phix, phiy)

    with np.errstate(divide="ignore", invalid="ignore"):
        hx = np.divide(phix, phimag, out=wu.copy(), where=phimag > 0)
        hy = np.divide(phiy, phimag, out=wv.copy(), where=phimag > 0)
    hx = np.nan_to_num(hx)
    hy = np.nan_to_num(hy)

    phimag = np.nan_to_num(phimag)
    r_head = np.nan_to_num(ros_base_ms) * (1.0 + phimag) * params.ros_mult
    r_head = np.where(burnable, np.minimum(np.nan_to_num(r_head), params.spread_cap_ms), 0.0)

    # elliptical eccentricity from length-to-breadth (Anderson 1983)
    umid = wind_speed * params.midflame_factor * MPH_PER_MS
    lb = np.clip(0.936 * np.exp(0.2566 * umid) + 0.461 * np.exp(-0.1548 * umid) - 0.397, 1.0, 8.0)
    ecc = np.sqrt(np.clip(1.0 - 1.0 / lb**2, 0.0, 0.999))

    return {"r_head": r_head, "hx": hx, "hy": hy, "ecc": ecc, "burnable": burnable}


def solve_arrival_times(
    grid: FireGrid, ignition_mask: np.ndarray, params: SpreadParams
) -> np.ndarray:
    """Multi-source Dijkstra -> arrival time (minutes) at each cell; np.inf where unreached."""
    ros = precompute_ros(grid, params)
    r_head, hx, hy, ecc = ros["r_head"], ros["hx"], ros["hy"], ros["ecc"]
    ny, nx = grid.ny, grid.nx
    cell = grid.cell_m

    arrival = np.full((ny, nx), np.inf)
    heap: list[tuple[float, int, int]] = []
    for i, j in zip(*np.nonzero(ignition_mask), strict=False):
        arrival[i, j] = 0.0
        heapq.heappush(heap, (0.0, int(i), int(j)))

    # precompute neighbour unit directions & distances
    dirs = []
    for di, dj in _NEIGHBORS:
        dist = cell * np.hypot(di, dj)
        norm = np.hypot(di, dj)
        dirs.append((di, dj, dist, dj / norm, di / norm))  # dx=east=+dj, dy=north=+di

    while heap:
        t, i, j = heapq.heappop(heap)
        if t > arrival[i, j]:
            continue
        rh = r_head[i, j]
        if rh <= 1e-6:
            continue  # non-burnable / stalled cell does not propagate
        e = ecc[i, j]
        hxi, hyi = hx[i, j], hy[i, j]
        for di, dj, dist, dx, dy in dirs:
            ni, nj = i + di, j + dj
            if ni < 0 or ni >= ny or nj < 0 or nj >= nx:
                continue
            cos_th = dx * hxi + dy * hyi
            r_dir = rh * (1.0 - e) / (1.0 - e * cos_th)
            if r_dir <= 1e-9:
                continue
            nt = t + (dist / r_dir) / 60.0  # seconds -> minutes
            if nt < arrival[ni, nj]:
                arrival[ni, nj] = nt
                heapq.heappush(heap, (nt, ni, nj))
    return arrival


def burned_mask(arrival: np.ndarray, horizon_min: float) -> np.ndarray:
    return arrival <= horizon_min


def perimeter_polygon(grid: FireGrid, arrival: np.ndarray, horizon_min: float):
    """Lon/lat polygon of the burned area at `horizon_min`."""
    return grid.mask_to_polygon(burned_mask(arrival, horizon_min))
