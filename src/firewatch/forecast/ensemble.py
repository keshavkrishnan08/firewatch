"""Forecast ensemble: N perturbed members -> a calibrated burn-probability field (FR-FC-2, FR-FC-4).

Each member perturbs wind, fuel moisture, ignition location, and a global ROS multiplier, then runs
the MTT spread solver. The (weighted) fraction of members that have burned a cell by a given horizon
IS the burn-probability. Weights are uniform for the no-assimilation baseline and set by the particle
filter (`assimilation.py`) for the assimilation arm — that difference is the ON/OFF ablation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry.base import BaseGeometry

from firewatch.forecast.grid import FireGrid
from firewatch.forecast.spread import SpreadParams, burned_mask, solve_arrival_times


@dataclass
class Member:
    params: SpreadParams
    ignition_lonlat: tuple[float, float]
    weight: float = 1.0
    arrival: np.ndarray | None = None  # (ny, nx) minutes, filled by run()


@dataclass
class EnsembleConfig:
    n_members: int = 60
    wind_mult_sd: float = 0.20
    wind_dir_sd_deg: float = 15.0
    moisture_mult_sd: float = 0.25
    ros_mult_sd: float = 0.20
    ignition_sd_m: float = 300.0
    ignition_radius_m: float = 150.0
    spread_cap_ms: float = 3.0
    # Fast-tail mixture: a fraction of members drawn from a faster wind/spread prior. Real
    # wind-driven runs have a heavy fast tail, so this widens the credible envelope (honest
    # coverage) while the tight core keeps the p>=0.5 point forecast (IoU) near the median.
    tail_frac: float = 0.0
    tail_wind_mult: float = 1.8
    tail_wind_mult_sd: float = 0.5
    tail_spread_cap_ms: float = 12.0
    seed: int = 12


class Ensemble:
    def __init__(self, grid: FireGrid, members: list[Member], config: EnsembleConfig,
                 initial_mask=None):
        self.grid = grid
        self.members = members
        self.config = config
        #: optional already-burned mask (forecast an ongoing fire forward from its current perimeter)
        self.initial_mask = initial_mask

    # ── construction ────────────────────────────────────────────────────────────

    @classmethod
    def generate(
        cls,
        grid: FireGrid,
        ignition_lonlat: tuple[float, float],
        config: EnsembleConfig | None = None,
        initial_mask=None,
    ) -> Ensemble:
        cfg = config or EnsembleConfig()
        rng = np.random.default_rng(cfg.seed)
        members: list[Member] = []
        n_tail = int(round(cfg.tail_frac * cfg.n_members))
        for i in range(cfg.n_members):
            dx = rng.normal(0, cfg.ignition_sd_m)
            dy = rng.normal(0, cfg.ignition_sd_m)
            lon0, lat0 = ignition_lonlat
            # offset ignition in the local meter frame
            x, y = grid.projector.to_local(lon0, lat0)
            lon, lat = grid.projector.to_wgs84(x + dx, y + dy)
            # tight core keeps the median (point forecast / IoU); the fast-tail members reach beyond
            # it so the credible envelope honestly covers the real fire's fingers.
            tail = i >= cfg.n_members - n_tail
            if tail:
                wm = float(np.clip(rng.normal(cfg.tail_wind_mult, cfg.tail_wind_mult_sd), 0.6, 4.0))
                cap = cfg.tail_spread_cap_ms
            else:
                wm = float(np.clip(rng.normal(1.0, cfg.wind_mult_sd), 0.4, 2.4))
                cap = cfg.spread_cap_ms
            params = SpreadParams(
                wind_mult=wm,
                wind_dir_offset_deg=float(rng.normal(0.0, cfg.wind_dir_sd_deg * (1.4 if tail else 1.0))),
                moisture_mult=float(np.clip(rng.normal(1.0, cfg.moisture_mult_sd), 0.35, 2.4)),
                ros_mult=float(np.clip(rng.normal(1.0, cfg.ros_mult_sd), 0.4, 3.0)),
                spread_cap_ms=cap,
            )
            members.append(Member(params=params, ignition_lonlat=(float(lon), float(lat))))
        return cls(grid, members, cfg, initial_mask=initial_mask)

    # ── running ─────────────────────────────────────────────────────────────────

    def run(self, surrogate=None) -> Ensemble:
        """Solve each member's arrival field. If a learned `surrogate` is given, use it (fast prior)
        instead of the physical MTT solver — the assimilation/calibration loop is unchanged."""
        for m in self.members:
            if surrogate is not None and self.initial_mask is None:
                m.arrival = surrogate.predict_arrival(self.grid, m.ignition_lonlat, m.params)
                continue
            if self.initial_mask is not None:
                ign = self.initial_mask  # forecast forward from the current observed perimeter
            else:
                ign = self.grid.ignition_mask(m.ignition_lonlat, radius_m=self.config.ignition_radius_m)
            m.arrival = solve_arrival_times(self.grid, ign, m.params)
        return self

    def _weights(self) -> np.ndarray:
        w = np.array([m.weight for m in self.members], dtype=float)
        s = w.sum()
        return w / s if s > 0 else np.full(len(self.members), 1.0 / len(self.members))

    def effective_sample_size(self) -> float:
        w = self._weights()
        return float(1.0 / np.sum(w**2))

    # ── products ────────────────────────────────────────────────────────────────

    def burn_probability(self, horizon_min: float) -> np.ndarray:
        """Weighted P(cell burned by horizon) in [0, 1]."""
        w = self._weights()
        acc = np.zeros((self.grid.ny, self.grid.nx))
        for wi, m in zip(w, self.members, strict=False):
            if m.arrival is None:
                continue
            acc += wi * burned_mask(m.arrival, horizon_min)
        return acc

    def expected_perimeter(self, horizon_min: float, level: float = 0.5) -> BaseGeometry | None:
        p = self.burn_probability(horizon_min)
        return self.grid.mask_to_polygon(p >= level)

    def region_at_prob(self, horizon_min: float, tau: float) -> BaseGeometry | None:
        """Credible envelope: cells with burn-prob ≥ tau (smaller tau → larger region)."""
        p = self.burn_probability(horizon_min)
        return self.grid.mask_to_polygon(p >= tau)

    def region_90(self, horizon_min: float) -> BaseGeometry | None:
        """The 90% credible burn region (prior τ=0.1; empirical coverage reported in calibration)."""
        return self.region_at_prob(horizon_min, 0.10)

    def mean_arrival(self) -> np.ndarray:
        w = self._weights()
        stack = np.stack([np.nan_to_num(m.arrival, posinf=1e9) for m in self.members])
        return np.average(stack, axis=0, weights=w)
