*Part of the FIREWATCH spec, see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH, Ontology (objects · links · actions)

The ontology is the spine of FIREWATCH and the single source of truth. Every module reads and writes these objects; nothing passes raw feed payloads around. This is deliberately Foundry-shaped: **objects** (nouns), **links** (relationships), **actions** (the verbs that change state, logged with their evidence). If a reviewer asks "how is this different from a model," the answer is: *this.*

All objects are **time-stamped and versioned** so state is reconstructable at any past instant and projectable to future instants. All geometry is stored EPSG:4326.

## Objects

| Object | Key fields | Notes |
|---|---|---|
| **Fire** | `id`, `name`, `discovered_at`, `status`, `centroid`, `ignition_estimate` | The incident. Anchors everything. |
| **FirePerimeter** | `fire_id`, `t`, `geometry`, `source`, `confidence` | Observed *or* forecast perimeter at time `t`. Forecast ones carry a probability field ref. |
| **Observation** | `id`, `fire_id`, `t`, `kind{goes,viirs,modis,camera_front,official_perimeter}`, `geometry/value`, `provenance`, `reported_uncertainty` | The atoms the filter assimilates. Provenance is mandatory. |
| **Forecast** | `fire_id`, `issued_at`, `horizon`, `prob_field` (raster), `expected_perimeter`, `region_90`, `calibration_ref` | Output of the assimilation loop per horizon. |
| **Camera** | `id`, `lat/lon/elev`, `pan/tilt/fov`, `network`, `pose_uncertainty`, `last_frame` | Pose feeds georeferencing; tilt often approximate → self-calibrated. |
| **WeatherCell** | `bbox`, `t`, `wind_u/v`, `rh`, `temp`, `source` | HRRR grid / RAWS stations. Drives ROS + ensemble perturbation. |
| **TerrainCell** | `bbox`, `elev`, `slope`, `aspect` | From DEM. Static. Drives ROS + ray-cast. |
| **FuelCell** | `bbox`, `fuel_model`, `canopy`, `moisture_est` | LANDFIRE. Drives ROS; moisture is an ensemble-perturbed unknown. |
| **Structure** | `id`, `footprint`, `type`, `population_est` | MS/OSM footprints × census. Exposure target. |
| **PopulationZone** | `id`, `geometry`, `population`, `evac_status` | County evac zones where available, else census blocks. |
| **RoadSegment** | `id`, `geometry`, `graph_edge`, `capacity` | OSM. Egress routing + threat timing. |
| **Resource** | `id`, `kind{crew,engine,air}`, `location`, `status` | For staging suggestions (where public). |
| **Recommendation** | `id`, `kind{evacuate,close_road,stage}`, `target`, `lead_time`, `confidence`, `evidence[]`, `issued_at` | The decision-layer output. Human-in-the-loop; `evidence[]` links the objects that justify it. |

## Links
- `Fire` -has→ `FirePerimeter[]`, `Observation[]`, `Forecast[]`
- `Observation` -from→ `Camera` | (satellite product) | (official source)
- `Camera` -sees→ `Fire` (when a plume is georeferenced into the fire's area)
- `Forecast` -threatens→ `Structure[]` | `PopulationZone[]` | `RoadSegment[]` (prob over threshold within horizon)
- `Recommendation` -protects→ `PopulationZone` | `RoadSegment`; -justified_by→ `Observation[]`/`Forecast`
- `TerrainCell`/`FuelCell`/`WeatherCell` -force→ `Forecast` (inputs to spread ROS)

## Actions (verbs; each logged with evidence + issuing agent = human)
- `ingest_observation(obs)`, write an Observation (with provenance).
- `assimilate()`, run one filter update; produces/updates `Forecast` objects.
- `georeference_camera_front(camera, mask)`, emit a `camera_front` Observation + uncertainty.
- `recommend_evacuation(zone)`, create a `Recommendation` with lead-time, confidence, evidence.
- `recommend_road_closure(segment)` / `recommend_staging(point)`, analogous.
- `acknowledge/override(recommendation, user)`, human decision recorded (never automated).

## Why this matters for the pitch
- **Integration story:** heterogeneous public feeds collapse into one queryable world model.
- **Auditability:** every recommendation traces to the observations and forecast that produced it (`Recommendation.evidence[]`).
- **Time travel:** versioned objects give the scrubber and the retrospective replay for free.
- **NL query (stretch):** natural-language questions map to read-only ontology queries; answers cite object ids.
