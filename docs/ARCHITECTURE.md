*Part of the FIREWATCH spec — see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH — Architecture

Companion to `PRD.md` (requirements) and `ONTOLOGY.md` (the object model). This doc is the "how it fits together." Module boundaries here map 1:1 to `src/firewatch/`.

## 1. Design principles
- **Ontology as the bus.** Modules never hand each other raw feed payloads. Ingestion writes `Observation` and layer objects; perception/forecast/decision read and write ontology objects. This decoupling is what makes it feel like Foundry and keeps subsystems independently testable.
- **Multi-rate by design.** Observations arrive at wildly different cadences (GOES ~5 min, VIIRS a few times/day, cameras ~1/min, HRRR hourly, official perimeters occasionally). The assimilation loop is event-driven: any new observation triggers an update.
- **Everything time-stamped & versioned.** State is reconstructable at any past instant and projectable to future instants; the UI scrubber is just a query over object versions.
- **Uncertainty flows end to end.** Observations carry uncertainty → ensemble represents it → forecast emits probability fields → decisions carry confidence + lead-time bands.

## 2. Data flow (one assimilation cycle)
```
                         ┌─────────────────────────────────────────────┐
   PUBLIC FEEDS          │                 INGEST                       │
 ─────────────────       │  FIRMS  GOES-FDC  HRRR  DEM  LANDFIRE        │
  cameras ─┐             │  NIFC   camera-tiles  assets(OSM/census)     │
  GOES ─┐  │             └───────────────┬─────────────────────────────┘
  VIIRS │  │                             │ writes Observation + layer objects
  HRRR  │  │                             ▼
  NIFC  │  │             ┌─────────────────────────────────────────────┐
        │  └───frames───▶│              PERCEPTION                      │
        │                │  detector(YOLO/RT-DETR) → SAM2 masks →       │
        │                │  smoke-state features → GEOREFERENCE(DEM)    │
        │                │  → georeferenced front + uncertainty         │
        │                └───────────────┬─────────────────────────────┘
        │                                │ writes camera-front Observation
        ▼                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                             ONTOLOGY (source of truth)                 │
 │   Fire · Perimeter(t) · Observation · Camera · Weather · Terrain ·     │
 │   Fuel · Structure · PopulationZone · RoadSegment · Resource · Rec.    │
 └───────────────┬───────────────────────────────────────┬──────────────┘
                 │ reads forcing + observations           │ reads forecast + assets
                 ▼                                        ▼
 ┌───────────────────────────────┐        ┌──────────────────────────────┐
 │           FORECAST            │        │           DECISION            │
 │  spread prior (Rothermel/CA/  │  fcast │  risk-to-population           │
 │  level-set) → ENSEMBLE →      │───────▶│  evacuation lead-time         │
 │  ASSIMILATE(obs) → prob field │        │  egress-route threat          │
 │  + calibrated 90% region      │        │  staging suggestions          │
 └───────────────┬───────────────┘        └───────────────┬──────────────┘
                 │ writes Forecast objects                 │ writes Recommendation objects
                 └───────────────────┬─────────────────────┘
                                     ▼
                        ┌──────────────────────────┐
                        │           API             │  FastAPI → COP board
                        │  /state /forecast         │  (MapLibre + deck.gl)
                        │  /decisions /observe      │  time scrubber, 3 panes
                        │  /query (NL, stretch)     │
                        └──────────────────────────┘
```

## 3. Modules (→ `src/firewatch/`)
### 3.1 `ingest/`
- One connector per feed: `firms.py`, `goes.py`, `hrrr.py`, `dem.py`, `landfire.py`, `perimeters.py`, `cameras.py`, `assets.py`.
- Contract: `fetch(bbox, t0, t1) -> list[Observation | Layer]`, each with **provenance**.
- `replay.py`: given `event_id`, pin & cache historical snapshots for offline reproducibility.
- Degrade gracefully: a failing connector logs + yields nothing; it must not crash the cycle.
### 3.2 `perception/`
- `detect.py`: YOLO/RT-DETR smoke/flame boxes per frame.
- `segment.py`: SAM2 promptable video segmentation → per-frame masks + track ids.
- `features.py`: mask area, centroid, bearing-from-camera, growth rate, plume tilt, confidence.
- `georeference.py` **(novelty 1)**: camera pose + mask → DEM ray-cast → ground front + uncertainty; `skyline.py` self-calibrates PTZ tilt by matching imaged horizon to DEM-rendered horizon; `triangulate.py` fuses ≥2 cameras.
### 3.3 `ontology/`
- `objects.py` (dataclasses/pydantic for each object), `links.py`, `actions.py`, `store.py` (versioned, time-indexed; SQLite/DuckDB + GeoParquet is plenty for v1).
- All geometry stored EPSG:4326; math done in an appropriate projected CRS.
### 3.4 `forecast/` **(research core)**
- `spread.py`: Rothermel ROS + level-set/CA front propagation on the fuel/slope/wind grid.
- `ensemble.py`: N members with perturbed wind/fuel-moisture/ignition/ROS params.
- `assimilation.py`: ensemble/particle filter; perimeter/front observation operator + matching scheme (front-distance likelihood; optional morphing amplitude+displacement correction); provenance-weighted observation error; spurious-fire regularization.
- `surrogate.py` (optional): NN emulator pretrained on WildfireSpreadTS/Next-Day for a faster prior.
- `calibrate.py`: temperature scaling / isotonic on the burn-probability field.
### 3.5 `decision/`
- `risk.py` (prob × footprints × population), `evacuation.py` (lead-time per zone + confidence), `routing.py` (egress-segment time-to-threat over OSM graph), `staging.py` (safe staging points).
- Output is always `Recommendation` objects with evidence links (auditable).
### 3.6 `api/`
- `server.py` (FastAPI), `schemas.py`, `query.py` (NL→ontology, read-only, stretch).
- Frontend `web/` (MapLibre + deck.gl): three panes + scrubber.

## 4. Key technical choices & rationale
- **Level-set/CA prior over a full physics simulator:** transparent, debuggable, laptop-fast, and sufficient as the ensemble mean the filter corrects. WRF-SFIRE is the reference, not the target.
- **Ensemble/particle filter over a learned end-to-end forecaster:** the contribution is the *assimilation + calibration*, which needs an explicit uncertainty representation and an observation operator. A learned surrogate can accelerate the prior but doesn't replace the loop.
- **DEM ray-casting for georeferencing:** matches the validated method line (Santana; monoplotting); the novel part is automation + skyline self-cal + uncertainty, not the ray-cast itself.
- **DuckDB/GeoParquet ontology store:** trivial to set up, versioned queries, no server; scales fine for single-fire, single-workstation v1.

## 5. Deployment / runtime
- Single workstation with one consumer GPU (perception + surrogate) or CPU-only for the physical prior. All feeds free/public. `docker-compose` for API+frontend; `make replay FIRE=<id>` for the offline reproducible path used in evaluation and demos.

## 6. What is intentionally NOT here (v1)
3D reconstruction, cross-region domain adaptation as a headline, and any autonomous-action path. The NL query endpoint is read-only and added last. See `PRD.md` §3.2.
