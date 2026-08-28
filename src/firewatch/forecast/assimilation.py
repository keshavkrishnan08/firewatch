"""Observation assimilation for the spread ensemble (RESEARCH CORE, FR-FC-3).

We use a **regularized particle filter**. Each ensemble member is a particle (a parameter draw +
its MTT arrival-time map). When an observation arrives (GOES/VIIRS hotspots, a georeferenced camera
front, or an official perimeter), we score every member by how well its *predicted* burned area at
the observation time matches the observation, weight the members by that likelihood, and resample
with parameter jitter when the effective sample size collapses. Between/after observations we
re-forecast forward from the reweighted ensemble.

Why a particle filter rather than an EnKF: front/perimeter observations are strongly nonlinear and
the classic EnKF failure mode here is *spurious fires* from unconstrained additive perturbations
(Beezley & Mandel 2008). A PF avoids that entirely, likelihoods only ever reweight physically-run
members, and we further regularize by (a) capping head ROS (`SpreadParams.spread_cap_ms`) and
(b) jittering on resample to keep diversity. Observation error is weighted by provenance (FR-ING-3).

Lineage: Mandel 2008/2009; Beezley & Mandel 2008; Rochoux & Trouvé 2014 (see docs/REFERENCES.md).
The contribution is the *accessible, fused, calibrated* packaging, not the filter itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from firewatch.forecast.ensemble import Ensemble, Member
from firewatch.forecast.grid import FireGrid
from firewatch.forecast.spread import SpreadParams, burned_mask, solve_arrival_times
from firewatch.geo import from_geojson
from firewatch.ontology.objects import Observation, ObservationKind

# default 1-sigma observation errors (meters) by product, used if provenance omits it
DEFAULT_SIGMA_M: dict[str, float] = {
    ObservationKind.goes.value: 2000.0,
    ObservationKind.viirs.value: 375.0,
    ObservationKind.modis.value: 1000.0,
    ObservationKind.camera_front.value: 500.0,
    ObservationKind.official_perimeter.value: 120.0,
}


@dataclass
class AssimObs:
    """An observation normalized into the local grid frame for the filter."""

    minutes: float  # minutes since ignition (matches member arrival maps)
    geom_local: BaseGeometry  # projected to local meters
    sigma_m: float
    kind: str
    is_area: bool  # True for perimeters/polygons; False for hotspot point sets


def observation_to_assim(
    obs: Observation, grid: FireGrid, ignition_time: datetime
) -> AssimObs | None:
    """Convert an ontology Observation into an `AssimObs` (or None if it has no usable geometry)."""
    geom = from_geojson(obs.geometry)
    if geom is None or geom.is_empty:
        return None
    minutes = (obs.t - ignition_time).total_seconds() / 60.0
    sigma = obs.reported_uncertainty_m or (obs.provenance.reported_uncertainty_m if obs.provenance else None)
    if not sigma:
        sigma = DEFAULT_SIGMA_M.get(obs.kind.value, 750.0)
    sigma = max(float(sigma), grid.cell_m)
    local = grid.projector.geom_to_local(geom)
    is_area = geom.geom_type in ("Polygon", "MultiPolygon")
    return AssimObs(minutes=minutes, geom_local=local, sigma_m=sigma, kind=obs.kind.value, is_area=is_area)


@dataclass
class ParticleFilterConfig:
    ess_frac_threshold: float = 0.5  # resample when ESS < frac * N
    jitter_wind_mult: float = 0.05
    jitter_wind_dir_deg: float = 3.0
    jitter_moisture_mult: float = 0.05
    jitter_ros_mult: float = 0.05
    over_prediction_weight: float = 0.4  # weight of over-prediction term for area obs
    seed: int = 99


class ParticleFilter:
    def __init__(self, grid: FireGrid, config: ParticleFilterConfig | None = None):
        self.grid = grid
        self.config = config or ParticleFilterConfig()
        self.rng = np.random.default_rng(self.config.seed)
        self._cell_area = grid.cell_m**2
        # cell-center local coordinates (for point membership / rasterization)
        self._XX, self._YY = np.meshgrid(grid._xs, grid._ys)

    # ── observation operator ────────────────────────────────────────────────────

    def _rasterize(self, geom_local: BaseGeometry) -> np.ndarray:
        """Boolean mask of cells whose centers fall inside a projected polygon."""
        from matplotlib.path import Path as MplPath

        pts = np.column_stack([self._XX.ravel(), self._YY.ravel()])
        mask = np.zeros(pts.shape[0], dtype=bool)
        polys = geom_local.geoms if geom_local.geom_type == "MultiPolygon" else [geom_local]
        for poly in polys:
            path = MplPath(np.asarray(poly.exterior.coords))
            mask |= path.contains_points(pts)
        return mask.reshape(self._XX.shape)

    def _points_to_cells(self, geom_local: BaseGeometry) -> list[tuple[int, int]]:
        if geom_local.geom_type in ("MultiPoint", "GeometryCollection"):
            coords = [(g.x, g.y) for g in geom_local.geoms if isinstance(g, Point)]
        elif geom_local.geom_type == "Point":
            coords = [(geom_local.x, geom_local.y)]
        else:  # polygon/line: use representative boundary + centroid points
            coords = list(geom_local.exterior.coords) if hasattr(geom_local, "exterior") else list(geom_local.coords)
        cells = []
        for x, y in coords:
            j = int(round(x / self.grid.cell_m + (self.grid.nx - 1) / 2.0))
            i = int(round(y / self.grid.cell_m + (self.grid.ny - 1) / 2.0))
            if self.grid.in_bounds(i, j):
                cells.append((i, j))
        return cells

    def distance(self, member: Member, obs: AssimObs) -> float:
        """Mismatch (meters) between a member's predicted burned area at obs time and the obs."""
        assert member.arrival is not None
        pred = burned_mask(member.arrival, obs.minutes)
        if not pred.any():
            # nothing burned yet in this member: large but finite mismatch
            return 5.0 * obs.sigma_m
        edt_pred = distance_transform_edt(~pred) * self.grid.cell_m  # dist to nearest burned cell

        if obs.is_area:
            obs_mask = self._rasterize(obs.geom_local)
            if not obs_mask.any():
                return 5.0 * obs.sigma_m
            edt_obs = distance_transform_edt(~obs_mask) * self.grid.cell_m
            # average surface distance both ways -> penalizes under- AND over-prediction
            under = edt_pred[obs_mask].mean()  # obs area the member failed to burn
            over = edt_obs[pred].mean()  # member area outside the observed perimeter
            return float(under + self.config.over_prediction_weight * over)

        cells = self._points_to_cells(obs.geom_local)
        if not cells:
            return 5.0 * obs.sigma_m
        d = np.array([edt_pred[i, j] for i, j in cells])
        return float(np.sqrt(np.mean(d**2)))

    def likelihood(self, member: Member, obs: AssimObs) -> float:
        d = self.distance(member, obs)
        return float(np.exp(-0.5 * (d / obs.sigma_m) ** 2))

    # ── filter steps ────────────────────────────────────────────────────────────

    def update(self, ensemble: Ensemble, obs_batch: list[AssimObs]) -> None:
        """Reweight the ensemble against a batch of same-time observations; resample if degenerate."""
        for m in ensemble.members:
            lik = 1.0
            for obs in obs_batch:
                lik *= max(self.likelihood(m, obs), 1e-12)
            m.weight *= lik
        # normalize
        total = sum(m.weight for m in ensemble.members)
        if total <= 0:
            for m in ensemble.members:
                m.weight = 1.0 / len(ensemble.members)
        else:
            for m in ensemble.members:
                m.weight /= total
        if ensemble.effective_sample_size() < self.config.ess_frac_threshold * len(ensemble.members):
            self._resample(ensemble)

    def _resample(self, ensemble: Ensemble) -> None:
        """Systematic resampling with parameter jitter (regularized PF), then re-run new members."""
        n = len(ensemble.members)
        w = np.array([m.weight for m in ensemble.members])
        w = w / w.sum()
        positions = (self.rng.random() + np.arange(n)) / n
        cumsum = np.cumsum(w)
        idx = np.searchsorted(cumsum, positions)
        idx = np.clip(idx, 0, n - 1)

        c = self.config
        new_members: list[Member] = []
        for k in idx:
            src = ensemble.members[k]
            p = src.params
            jittered = SpreadParams(
                wind_mult=float(np.clip(p.wind_mult + self.rng.normal(0, c.jitter_wind_mult), 0.3, 2.5)),
                wind_dir_offset_deg=float(p.wind_dir_offset_deg + self.rng.normal(0, c.jitter_wind_dir_deg)),
                moisture_mult=float(np.clip(p.moisture_mult + self.rng.normal(0, c.jitter_moisture_mult), 0.3, 2.5)),
                ros_mult=float(np.clip(p.ros_mult + self.rng.normal(0, c.jitter_ros_mult), 0.3, 2.5)),
                ignition_offset_m=p.ignition_offset_m,
                spread_cap_ms=p.spread_cap_ms,
                midflame_factor=p.midflame_factor,
            )
            m = Member(params=jittered, ignition_lonlat=src.ignition_lonlat, weight=1.0 / n)
            if ensemble.initial_mask is not None:
                ign = ensemble.initial_mask
            else:
                ign = self.grid.ignition_mask(m.ignition_lonlat, radius_m=ensemble.config.ignition_radius_m)
            m.arrival = solve_arrival_times(self.grid, ign, jittered)
            new_members.append(m)
        ensemble.members = new_members


def assimilate_sequence(
    ensemble: Ensemble,
    observations: list[Observation],
    ignition_time: datetime,
    grid: FireGrid,
    config: ParticleFilterConfig | None = None,
) -> ParticleFilter:
    """Sequentially assimilate time-ordered observations into the ensemble (in place).

    Observations at the same timestamp are batched. Returns the filter (for reuse/inspection).
    Causal by construction: only observations with t ≤ their own timestamp inform the weights.
    """
    pf = ParticleFilter(grid, config)
    obs_sorted = sorted(observations, key=lambda o: o.t)
    batch: list[AssimObs] = []
    batch_t = None
    for o in obs_sorted:
        a = observation_to_assim(o, grid, ignition_time)
        if a is None:
            continue
        if batch_t is not None and o.t != batch_t and batch:
            pf.update(ensemble, batch)
            batch = []
        batch_t = o.t
        batch.append(a)
    if batch:
        pf.update(ensemble, batch)
    return pf
