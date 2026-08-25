"""Shared spatial-exposure helpers for the decision layer.

Everything the decision modules need reduces to: which grid cells does an asset (zone / road /
structure) occupy, and what is the ensemble's *arrival-time distribution* into those cells. From
that distribution we get burn probability by any horizon, a lead-time, and a confidence band —
all with the ensemble spread carried through (uncertainty is first-class, CLAUDE.md principle 4).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry.base import BaseGeometry

from firewatch.forecast.ensemble import Ensemble
from firewatch.forecast.grid import FireGrid


def cells_in_geom(grid: FireGrid, geom: BaseGeometry) -> np.ndarray:
    """Boolean grid mask of cells whose centers fall in a lon/lat geometry (polygon or buffered line)."""
    from matplotlib.path import Path as MplPath

    local = grid.projector.geom_to_local(geom)
    XX, YY = np.meshgrid(grid._xs, grid._ys)
    pts = np.column_stack([XX.ravel(), YY.ravel()])
    mask = np.zeros(pts.shape[0], dtype=bool)
    if local.geom_type in ("LineString", "MultiLineString"):
        local = local.buffer(grid.cell_m)  # give roads width
    polys = local.geoms if local.geom_type == "MultiPolygon" else [local]
    for poly in polys:
        if poly.is_empty or not hasattr(poly, "exterior"):
            continue
        mask |= MplPath(np.asarray(poly.exterior.coords)).contains_points(pts)
    return mask.reshape(XX.shape)


@dataclass
class ArrivalDistribution:
    arrivals: np.ndarray  # minutes since ignition per member (inf if never)
    weights: np.ndarray

    def prob_burned_by(self, minutes: float) -> float:
        finite = self.arrivals <= minutes
        return float(np.sum(self.weights[finite]))

    def lead_time_minutes(self, threshold: float, now_minutes: float) -> float | None:
        """Minutes from `now` until P(burned) first reaches `threshold`; None if never within data."""
        order = np.argsort(self.arrivals)
        cum = np.cumsum(self.weights[order])
        reached = np.where(cum >= threshold)[0]
        if len(reached) == 0:
            return None
        t_cross = self.arrivals[order][reached[0]]
        if not np.isfinite(t_cross):
            return None
        return float(t_cross - now_minutes)

    def quantile_minutes(self, q: float) -> float | None:
        order = np.argsort(self.arrivals)
        cum = np.cumsum(self.weights[order])
        idx = np.where(cum >= q)[0]
        if len(idx) == 0:
            return None
        t = self.arrivals[order][idx[0]]
        return float(t) if np.isfinite(t) else None


def arrival_distribution(ensemble: Ensemble, mask: np.ndarray) -> ArrivalDistribution:
    """Per-member first-arrival time into the masked cells, with ensemble weights."""
    w = np.array([m.weight for m in ensemble.members], dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1.0 / len(w))
    arrivals = np.full(len(ensemble.members), np.inf)
    for k, m in enumerate(ensemble.members):
        if m.arrival is None:
            continue
        sub = m.arrival[mask]
        if sub.size and np.isfinite(sub).any():
            arrivals[k] = float(np.nanmin(np.where(np.isfinite(sub), sub, np.inf)))
    return ArrivalDistribution(arrivals=arrivals, weights=w)
