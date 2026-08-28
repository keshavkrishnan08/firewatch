"""End-to-end event pipeline (M1→M5 driver), shared by the offline demo and real replay.

Given an assembled `EventBundle` (grid + DEM + ontology objects + observations), this runs the
assimilating forecast (ON) and the no-assimilation baseline (OFF), derives the decision-layer
recommendations, writes everything back into the ontology, and emits the COP JSON + evaluation
figures the frontend and the writeup consume. Reproducible and causal by construction.

The multi-issue-time analyses (sharpening curve, lead-time delta) evolve a *single* ensemble through
time and assimilate observations incrementally, snapshotting metrics at each issue time, which is
both far cheaper than re-running and the physically correct sequential-assimilation semantics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from firewatch.config import EventPaths
from firewatch.decision.evacuation import recommend_evacuations
from firewatch.decision.exposure import arrival_distribution, cells_in_geom
from firewatch.decision.risk import population_at_risk, structures_exposed
from firewatch.decision.routing import egress_threat
from firewatch.decision.staging import suggest_staging
from firewatch.forecast.assimilation import ParticleFilter, observation_to_assim
from firewatch.forecast.engine import ForecastResult, run_forecast, skill_vs_truth
from firewatch.forecast.ensemble import Ensemble, EnsembleConfig
from firewatch.forecast.grid import FireGrid
from firewatch.forecast.spread import burned_mask
from firewatch.geo import iou, polygon_area_m2, to_geojson
from firewatch.ontology.objects import Camera, Fire, PopulationZone, RoadSegment, Structure
from firewatch.ontology.store import Store
from firewatch.terrain import DEM


@dataclass
class EventBundle:
    event_id: str
    store: Store
    grid: FireGrid
    dem: DEM
    fire: Fire
    ignition_lonlat: tuple[float, float]
    ignition_time: datetime
    zones: list[PopulationZone] = field(default_factory=list)
    roads: list[RoadSegment] = field(default_factory=list)
    structures: list[Structure] = field(default_factory=list)
    cameras: list[Camera] = field(default_factory=list)
    observations: list = field(default_factory=list)
    wind: dict = field(default_factory=dict)
    truth_arrival: np.ndarray | None = None  # demo only (labeled synthetic)
    initial_burned_mask: np.ndarray | None = None  # forecast a live fire forward from its perimeter
    note: str = ""


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _feature(geom, props: dict) -> dict:
    return {"type": "Feature", "geometry": geom, "properties": props}


def run_pipeline(
    bundle: EventBundle,
    issue_time: datetime,
    *,
    ensemble_config: EnsembleConfig | None = None,
    horizons: list[int] | None = None,
    write_outputs: bool = True,
) -> dict:
    cfg = ensemble_config or EnsembleConfig(n_members=60)

    off = run_forecast(bundle.grid, bundle.ignition_lonlat, bundle.ignition_time,
                       observations=bundle.observations, assimilate=False,
                       issued_at=issue_time, ensemble_config=cfg, horizons=horizons,
                       initial_mask=bundle.initial_burned_mask)
    on = run_forecast(bundle.grid, bundle.ignition_lonlat, bundle.ignition_time,
                      observations=bundle.observations, assimilate=True,
                      issued_at=issue_time, ensemble_config=cfg, horizons=horizons,
                      initial_mask=bundle.initial_burned_mask)

    fc_objs = on.to_ontology(bundle.fire.id)
    bundle.store.put_many(fc_objs)
    evidence_ids = [o.id for o in fc_objs] + [o.id for o in bundle.observations if o.t <= issue_time]

    evacs = recommend_evacuations(on, bundle.zones, evidence=evidence_ids)
    egress = egress_threat(on, bundle.roads, evidence=evidence_ids)
    staging = suggest_staging(on, bundle.ignition_lonlat, evidence=evidence_ids)
    bundle.store.put_many(evacs + egress + staging)
    risk = population_at_risk(on, bundle.zones)
    struct_summary = {h: structures_exposed(on, bundle.structures, h) for h in on.horizons}

    result = {
        "event_id": bundle.event_id, "issue_time": issue_time.isoformat(),
        "forecast_on": on, "forecast_off": off,
        "evacuations": evacs, "egress": egress, "staging": staging,
        "risk": risk, "structures": struct_summary,
    }
    if bundle.truth_arrival is not None:
        result["skill_on"] = skill_vs_truth(on, bundle.truth_arrival)
        result["skill_off"] = skill_vs_truth(off, bundle.truth_arrival)

    if write_outputs:
        cop = build_cop_json(bundle, on, off, evacs, egress, staging, risk, struct_summary,
                             result.get("skill_on"), result.get("skill_off"))
        paths = EventPaths(bundle.event_id).ensure()
        (paths.outputs / "cop.json").write_text(json.dumps(cop, indent=2, default=str))
        result["cop_path"] = str(paths.outputs / "cop.json")
    return result


# ── multi-issue-time evolution (shared by sharpening + lead-time) ────────────────


def _obs_batches(bundle: EventBundle):
    """Observations grouped by timestamp -> [(t, [AssimObs])], sorted."""
    batches: dict = {}
    for o in bundle.observations:
        a = observation_to_assim(o, bundle.grid, bundle.ignition_time)
        if a is not None:
            batches.setdefault(o.t, []).append(a)
    return sorted(batches.items(), key=lambda kv: kv[0])


def _evolve(bundle: EventBundle, issue_offsets: list[int], *, assimilate: bool,
            cfg: EnsembleConfig, region_horizon: int, lead_horizon: int) -> list[dict]:
    """Evolve one ensemble through the issue times, assimilating obs incrementally; snapshot metrics."""
    ens = Ensemble.generate(bundle.grid, bundle.ignition_lonlat, cfg,
                            initial_mask=bundle.initial_burned_mask).run()
    pf = ParticleFilter(bundle.grid) if assimilate else None
    batches = _obs_batches(bundle)
    zone_masks = {z.id: cells_in_geom(bundle.grid, z.geom()) for z in bundle.zones}
    bi = 0
    snaps = []
    for off_min in sorted(issue_offsets):
        issue_t = bundle.ignition_time + timedelta(minutes=off_min)
        if assimilate:
            while bi < len(batches) and batches[bi][0] <= issue_t:
                pf.update(ens, batches[bi][1])
                bi += 1
        p = ens.burn_probability(region_horizon)
        region = bundle.grid.mask_to_polygon(p >= 0.10)
        snap = {
            "issue_min": off_min,
            "region90_area_km2": (polygon_area_m2(region) / 1e6) if region is not None else 0.0,
            "n_obs_assimilated": bi if assimilate else 0,
            "zone_conf": {zid: arrival_distribution(ens, m).prob_burned_by(off_min + lead_horizon)
                          for zid, m in zone_masks.items()},
        }
        if bundle.truth_arrival is not None:
            truth_poly = bundle.grid.mask_to_polygon(burned_mask(bundle.truth_arrival, region_horizon))
            snap["iou"] = iou(bundle.grid.mask_to_polygon(p >= 0.5), truth_poly)
        snaps.append(snap)
    return snaps


def sharpening_series(bundle: EventBundle, issue_offsets_min: list[int], horizon: int,
                      cfg: EnsembleConfig | None = None) -> list[dict]:
    """Region-90 area at a fixed horizon vs issue time, the 'forecast sharpens' curve."""
    cfg = cfg or EnsembleConfig(n_members=48)
    snaps = _evolve(bundle, issue_offsets_min, assimilate=True, cfg=cfg,
                    region_horizon=horizon, lead_horizon=horizon)
    return [{k: s[k] for k in ("issue_min", "region90_area_km2", "n_obs_assimilated", *(["iou"] if "iou" in s else []))}
            for s in snaps]


def lead_time_analysis(bundle: EventBundle, issue_offsets_min: list[int], *, horizon: int = 120,
                       threshold: float = 0.5, confidence: float = 0.5,
                       cfg: EnsembleConfig | None = None) -> list[dict]:
    """'Moved-the-needle' (docs/EVALUATION.md §4): earliest issue time ON vs OFF flags each zone,
    and the warning lead-time that buys vs the truth arrival."""
    cfg = cfg or EnsembleConfig(n_members=48)
    on = _evolve(bundle, issue_offsets_min, assimilate=True, cfg=cfg, region_horizon=horizon, lead_horizon=horizon)
    off = _evolve(bundle, issue_offsets_min, assimilate=False, cfg=cfg, region_horizon=horizon, lead_horizon=horizon)

    truth = bundle.truth_arrival
    zone_masks = {z.id: cells_in_geom(bundle.grid, z.geom()) for z in bundle.zones}
    truth_arr = {}
    for z in bundle.zones:
        m = zone_masks[z.id]
        if truth is not None and m.any() and np.isfinite(truth[m]).any():
            truth_arr[z.id] = float(np.nanmin(np.where(np.isfinite(truth[m]), truth[m], np.inf)))
        else:
            truth_arr[z.id] = None

    def earliest_flag(snaps, zid):
        for s in snaps:
            if s["zone_conf"].get(zid, 0.0) >= confidence:
                return s["issue_min"]
        return None

    out = []
    for z in bundle.zones:
        ta = truth_arr[z.id]
        on_flag = earliest_flag(on, z.id)
        off_flag = earliest_flag(off, z.id)
        out.append({
            "zone_id": z.id, "zone": z.name, "population": z.population,
            "truth_arrival_min": ta, "on_flag_min": on_flag, "off_flag_min": off_flag,
            "on_lead_min": (ta - on_flag) if (ta is not None and on_flag is not None) else None,
            "off_lead_min": (ta - off_flag) if (ta is not None and off_flag is not None) else None,
            "lead_delta_min": ((off_flag - on_flag) if (on_flag is not None and off_flag is not None) else None),
        })
    return out


# ── COP JSON ─────────────────────────────────────────────────────────────────


def build_cop_json(bundle, on: ForecastResult, off: ForecastResult, evacs, egress, staging, risk,
                   struct_summary, skill_on, skill_off) -> dict:
    grid = bundle.grid
    corners = [grid.cell_to_lonlat(i, j) for i in (0, grid.ny - 1) for j in (0, grid.nx - 1)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    bbox = [min(lons), min(lats), max(lons), max(lats)]

    def fc_forecast(res: ForecastResult) -> dict:
        out = {}
        for h in res.horizons:
            out[str(h)] = {
                "expected": to_geojson(res.expected_perimeter.get(h)),
                "region90": to_geojson(res.region_90.get(h)),
                "bands": [{"level": lvl, "geometry": to_geojson(g)} for lvl, g in res.bands.get(h, [])],
                "region90_area_km2": (polygon_area_m2(res.region_90[h]) / 1e6) if res.region_90.get(h) else 0.0,
            }
        return out

    cameras = _fc([_feature({"type": "Point", "coordinates": [c.lon, c.lat]},
                            {"id": c.id, "name": c.name, "pan": c.pan_deg, "tilt": c.tilt_deg, "fov": c.fov_deg,
                             "network": c.network, "frame": c.last_frame})
                   for c in bundle.cameras])
    zones = _fc([_feature(z.geometry, {"id": z.id, "name": z.name, "population": z.population, "evac_status": z.evac_status}) for z in bundle.zones])
    roads = _fc([_feature(r.geometry, {"id": r.id, "name": r.name, "highway": r.highway}) for r in bundle.roads])
    structures = _fc([_feature(s.geom("footprint").centroid.__geo_interface__, {"id": s.id, "type": s.type, "pop": s.population_est}) for s in bundle.structures])

    obs_features = []
    for o in sorted(bundle.observations, key=lambda x: x.t):
        if o.geometry:
            obs_features.append(_feature(o.geometry, {"id": o.id, "kind": str(o.kind), "t": o.t.isoformat(), "source": o.provenance.source}))

    def rec_json(recs):
        return [{"id": r.id, "kind": str(r.kind), "target": r.target, "target_name": r.target_name,
                 "lead_time_min": r.lead_time_min, "lead_time_low_min": r.lead_time_low_min, "lead_time_high_min": r.lead_time_high_min,
                 "confidence": r.confidence, "urgency": r.urgency, "rationale": r.rationale,
                 "evidence": r.evidence, "geometry": r.geometry} for r in recs]

    cop = {
        "meta": {
            "event_id": bundle.event_id,
            "fire": {"id": bundle.fire.id, "name": bundle.fire.name, "status": str(bundle.fire.status),
                     "ignition": list(bundle.ignition_lonlat), "discovered_at": bundle.fire.discovered_at.isoformat()},
            "issued_at": on.issued_at.isoformat(), "ignition_time": bundle.ignition_time.isoformat(),
            "horizons": on.horizons, "assimilation": on.assimilated, "wind": bundle.wind, "bbox": bbox, "note": bundle.note,
        },
        "layers": {"cameras": cameras, "zones": zones, "roads": roads, "structures": structures, "observations": _fc(obs_features)},
        "forecast": {"on": fc_forecast(on), "off": fc_forecast(off)},
        "decisions": {"evacuations": rec_json(evacs), "egress": rec_json(egress), "staging": rec_json(staging),
                      "risk": risk, "structures": struct_summary},
    }
    if skill_on and skill_off:
        cop["evaluation"] = {
            "skill_on": skill_on, "skill_off": skill_off,
            "ablation": {str(h): {"iou_on": skill_on[h]["iou"], "iou_off": skill_off[h]["iou"],
                                  "dice_on": skill_on[h]["dice"], "dice_off": skill_off[h]["dice"]} for h in on.horizons},
        }
    return cop
