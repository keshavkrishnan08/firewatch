# FIREWATCH, Product Requirements (PRD)

**Status:** Draft v1.0 · **Last updated:** 2026-08-25
**Companion docs:** `LITERATURE_REVIEW.md`, `ARCHITECTURE.md`, `ONTOLOGY.md`, `DATA_SOURCES.md`, `ROADMAP.md`, `EVALUATION.md`, `REFERENCES.md`

---

## 1. Vision & framing

### 1.1 One-line

> An open-source, real-time wildfire common operating picture that fuses camera, satellite,
> weather, terrain, and fuels data into a continuously self-correcting probabilistic spread
> forecast and a human-in-the-loop decision layer, validated by retrospective replay of real fires.

### 1.2 The problem

Wildfire response is a decision problem under extreme time pressure and fragmented information.
Incident commanders and emergency managers juggle satellite hotspot emails, a wall of tower-camera
feeds, spot weather forecasts, paper/GIS fuel maps, and radio traffic, and must decide *who to
evacuate, when, and by which route*, and *where to put crews*, hours before the fire arrives. The
data to make these calls **exists and is largely public**, but it is not integrated, not projected
into a shared picture, not turned into a forward-looking probabilistic forecast, and not tied to the
specific assets and populations at risk.

Two technical gaps compound this (full treatment in `LITERATURE_REVIEW.md`):

- **Detection is saturated; forecasting-in-the-loop is not.** The literature is thick with smoke/
  flame detectors and single-shot next-day spread predictors, but thin on *real-time, observation-
  assimilating, uncertainty-calibrated* forecasting delivered as accessible open software.
- **Assimilation is trapped in heavyweight simulators.** The methods that continuously correct a
  fire forecast from live observations (ensemble/particle filters over coupled atmosphere-fire
  models) require HPC and expert operation, so they don't reach the accessible ML/operational world.

### 1.3 Why this shape (Palantir fit)

This PRD is deliberately shaped like a Foundry/AIP application: model the world as an **ontology** of
objects/links/actions; **integrate** heterogeneous feeds into that model; put a **decision layer**
with humans in the loop on top; and prove operational value on **real events**. §12 (Success Metrics)
and the M5 retrospective (`ROADMAP.md`) are the load-bearing parts of the project, not the model
architecture.

### 1.4 Non-negotiable positioning

FIREWATCH is **not** a wildfire detector, a Kaggle model, or a research toy. Detection is a means to
an end (an observation source). The product is **integration → assimilation → decision**.

---

## 2. Users & jobs-to-be-done

| Persona | Job-to-be-done | What FIREWATCH gives them |
|---|---|---|
| **Incident commander / duty officer** | Decide evacuation timing and resource staging under uncertainty | Probabilistic +30/+60/+180-min perimeter, lead-time-to-asset, staging suggestions |
| **Emergency manager (county)** | Know which zones/roads are threatened and when | Risk-to-population map, egress-route threat timeline, zone-level evacuation triggers |
| **GIS / intel analyst** | Turn scattered feeds into one picture; answer ad-hoc questions | The ontology + COP board + read-only natural-language query |
| **Researcher / reviewer (incl. fellowship)** | Judge whether the system actually works | Reproducible retrospective replays, calibration diagrams, honest failure analysis |

**Primary persona for v1:** the analyst/duty-officer building the picture and the forecast. The
IC-facing decision UI is the M5 payoff.

---

## 3. Goals & non-goals

### 3.1 Goals (v1)

- **G1.** Integrate ≥5 public feeds into a single live ontology for an active or replayed fire.
- **G2.** Perceive: detect + segment smoke/flame on tower-camera imagery.
- **G3.** **Georeference** camera-observed smoke to a lat/lon front with an uncertainty region. *(novelty 1)*
- **G4.** **Assimilate** GOES/VIIRS/camera observations into a probabilistic spread forecast that measurably improves over a no-assimilation baseline. *(novelty 2 / research core)*
- **G5.** Calibrated uncertainty (reliability diagram, Brier/CRPS), not point forecasts.
- **G6.** Decision layer: risk-to-population, evacuation lead-time, egress-route threat.
- **G7.** Retrospective validation on ≥1 real named fire showing earlier/better warning than baseline.
- **G8.** Fully reproducible, open-source, one-command event replay.

### 3.2 Non-goals (v1)

- **N1.** Autonomous action (issuing orders). Human-in-the-loop only.
- **N2.** Novel detector architecture. Use off-the-shelf YOLO/RT-DETR/SAM2.
- **N3.** 3D digital twin, cross-region domain adaptation as marquee results, **stretch only**.
- **N4.** Global coverage. Focus: California, extensible later.
- **N5.** Beating a full operational simulator (WRF-SFIRE) on physical fidelity. The bar is *usefulness + calibration + accessibility*.

---

## 4. Product surface (what a user sees)

Three-pane COP board:

1. **Observe**, live/replay camera with detector boxes + SAM2 plume mask; source toggles.
2. **Map**, observed perimeter, georeferenced camera front, probabilistic forecast bands (+30/+60/+180 min), wind vector, threatened assets, egress routes colored by threat time.
3. **Decide**, ranked panel: zones by evacuation urgency (lead-time + confidence), egress routes by time-to-threat, suggested staging locations; every item links back to the evidence in the ontology. Read-only NL query box (stretch).

A horizontal **time scrubber** (−history … now … +forecast) drives all three panes together.

---

## 5. Functional requirements

Requirements are labeled `FR-<area>-<n>` and mapped to milestones in `ROADMAP.md`.

### 5.1 Ingestion (`ingest/`)

- **FR-ING-1** Each feed has a connector exposing `fetch(bbox, t0, t1) -> list[Observation]`.
- **FR-ING-2** Feeds (v1): NASA FIRMS (VIIRS/MODIS active fire), GOES ABI Fire Detection & Characterization (~5-min cadence), NOAA HRRR (10-m wind, RH, temp), USGS 3DEP DEM, LANDFIRE (fuel model / canopy), NIFC/WFIGS (official perimeters, ground truth), ALERTCalifornia/ALERTWildfire camera tiles + station metadata.
- **FR-ING-3** Every `Observation` carries provenance {source, product, retrieved_at, native_resolution, reported_uncertainty}, required downstream for assimilation weighting.
- **FR-ING-4** Replay mode: given an event id + time range, fetch/cache the exact historical snapshots so any run is reproducible offline.
- **FR-ING-5** Graceful degradation: missing/late feeds must not crash the picture; the forecast widens its uncertainty instead.

### 5.2 Perception (`perception/`)

- **FR-PER-1** Detector (YOLO or RT-DETR) classifies smoke, flame, and (optional) structures/vehicles on camera frames at ≥ camera cadence (~1 fps).
- **FR-PER-2** SAM2 promptable video segmentation propagates a plume/flame mask across frames from the detector box, producing per-frame pixel masks + track ids.
- **FR-PER-3** Per-frame smoke-state features: mask area, centroid, bearing from camera, growth rate, plume-tilt (a wind proxy), confidence.
- **FR-PER-4** Detector runs on FIgLib/FLAME/AusSmoke-style data for training/eval; report time-to-detection vs. single-frame baseline.

### 5.3 Georeferencing (`perception/georeference.py`), **novelty 1**

- **FR-GEO-1** Given a camera pose (lat/lon/elev, pan/tilt/FOV) and a smoke mask, cast rays from the camera through mask pixels and intersect them with the DEM to estimate ground coordinates of the plume base / fire front.
- **FR-GEO-2** Output a **georeferenced front geometry + uncertainty region** (cone from pose error, tilt error, and plume-base ambiguity), not a single point.
- **FR-GEO-3** Handle unknown/approximate PTZ tilt: estimate/refine tilt by matching the imaged horizon/skyline to the DEM-rendered horizon.
- **FR-GEO-4** When ≥2 cameras see the same plume, triangulate for a tighter fix.
- **FR-GEO-5** Emit the result as an ontology `Observation` feeding the forecast (FR-FC-3).

### 5.4 Ontology (`ontology/`)

- **FR-ONT-1** Implement the object/link/action model in `ONTOLOGY.md` as the single source of truth; all modules read/write objects, never raw feed payloads.
- **FR-ONT-2** Objects are versioned/time-stamped so the time scrubber can reconstruct state at any past instant (and forecast future instants).
- **FR-ONT-3** Actions (e.g., "recommend evacuation for Zone X") are logged with the evidence (object ids) that justified them, auditability.

### 5.5 Forecast + assimilation (`forecast/`), **research core**

- **FR-FC-1** Baseline spread model: level-set / cellular-automaton front propagation driven by Rothermel-style rate-of-spread from fuel + slope + wind (a transparent physical prior).
- **FR-FC-2** Ensemble: run N members with perturbed inputs (wind, fuel moisture, ignition, ROS params) to represent forecast uncertainty.
- **FR-FC-3** **Assimilation loop:** at each observation time, update the ensemble against incoming observations (GOES/VIIRS hotspots, georeferenced camera front, official perimeter when available) via an ensemble/particle filter with a matching scheme for perimeter/front observations (cf. morphing-EnKF ideas), weighted by each observation's provenance uncertainty.
- **FR-FC-4** Output at each horizon (+15/+30/+60/+180 min): a **per-cell burn-probability field** + expected perimeter + a stated prediction region (e.g., 90%).
- **FR-FC-5** Optional learned surrogate: a small NN emulator trained on WildfireSpreadTS/Next-Day-Wildfire-Spread to speed up / improve the prior, but assimilation and calibration remain the contribution.
- **FR-FC-6** The forecast must **demonstrably improve** as observations arrive (ablation: assimilation ON vs OFF), and must be **calibrated**.

### 5.6 Decision layer (`decision/`)

- **FR-DEC-1** Risk-to-population: overlay burn-probability × building footprints × population → expected exposed structures/people over time.
- **FR-DEC-2** Evacuation lead-time: for each zone/asset, time until burn-probability crosses a threshold, with confidence band → ranked urgency list.
- **FR-DEC-3** Egress-route threat: for road segments, time-to-threat along evacuation routes; flag routes that close before a zone can clear.
- **FR-DEC-4** Staging suggestion: candidate resource-staging points that stay outside the 90% region for the forecast horizon while minimizing response distance.
- **FR-DEC-5** Every recommendation shows lead-time, confidence, and the evidence trail; nothing is phrased as an autonomous order.

### 5.7 API / serving (`api/`) & UI

- **FR-API-1** FastAPI endpoints: `/event/{id}/state?t=`, `/event/{id}/forecast?h=`, `/event/{id}/decisions`, `/observe/{camera_id}`.
- **FR-API-2** Frontend: MapLibre + deck.gl COP board (§4) driven by the time scrubber.
- **FR-API-3** (Stretch) NL query: translate natural-language questions into read-only ontology queries; answers cite object ids. Thin layer, added last.

---

## 6. Non-functional requirements

- **NFR-1 Latency:** an assimilation+forecast cycle completes in ≤ the observation cadence (target ≤ 60 s per cycle on a single workstation/GPU) so it can run "live."
- **NFR-2 Reproducibility:** `make replay FIRE=<id>` regenerates every headline figure; RNG seeded; data snapshots pinned.
- **NFR-3 Cost:** runs on one workstation (1 consumer GPU) or a modest cloud box; all data feeds free/public. No paid dependencies in the critical path.
- **NFR-4 Robustness:** any single feed can be absent; the system degrades (widens uncertainty) rather than failing.
- **NFR-5 Auditability:** every decision recommendation is traceable to the observations/objects that produced it.
- **NFR-6 Honesty:** docs distinguish "target" from "measured"; calibration + failure analysis shipped, not hidden.

---

## 7. Data requirements

Full access notes, endpoints, resolutions, and gotchas in `DATA_SOURCES.md`.

- **Observations for assimilation:** GOES ABI FDC hotspots (~5 min), VIIRS/MODIS active fire (FIRMS, ~few passes/day, 375 m), georeferenced camera fronts (FIREWATCH-derived), official perimeters (NIFC/WFIGS).
- **Static/forcing layers:** DEM (USGS 3DEP/SRTM), fuels/canopy (LANDFIRE), weather (NOAA HRRR).
- **Assets:** building footprints (MS/OSM), population (US Census), roads (OSM).
- **Training/eval datasets:** FIgLib + SmokeyNet, FLAME/FLAME2/AusSmoke, Next Day Wildfire Spread + WildfireSpreadTS + Mesogeos, MTBS + NIFC historical perimeters.

---

## 8. The ontology (summary)

Objects: **Fire**, **FirePerimeter (t)**, **Observation**, **Camera**, **WeatherCell**,
**TerrainCell**, **FuelCell**, **Structure**, **PopulationZone**, **RoadSegment**, **Resource**,
**Recommendation**. Links and actions in `ONTOLOGY.md`.

---

## 9. Milestones (summary, full criteria in `ROADMAP.md`)

M1 Live COP · M2 Perception · M3 Georeferencing · M4 Assimilating forecast · M5 Decision +
retrospective. Each is independently demoable.

---

## 10. Risks & mitigations (summary, full table in `ROADMAP.md`)

- **Camera pose imprecise** → skyline-to-DEM tilt refinement (FR-GEO-3); degrade to bearing-only.
- **Assimilation instability / spurious fires** → regularization + morphing/matching; particle-filter fallback; cap ensemble spread.
- **Sparse observations** → widen uncertainty honestly; lean on GOES cadence.
- **Scope creep** → milestone gates; stretch items fenced off.
- **Overclaiming novelty** → the gap analysis states prior art plainly.

---

## 11. Dependencies & stack

See `CLAUDE.md` (Tech stack) and `requirements.txt`. Everything free/open; single-GPU target.

---

## 12. Success metrics (this is what "done" means)

**Perception**
- Time-to-detection improvement vs. single-frame baseline on FIgLib-style sequences (Δ minutes).

**Georeferencing**
- Median ground-position error (meters) of the georeferenced front vs. official perimeter; report error vs. distance-to-fire and vs. terrain roughness.

**Forecast (the headline)**
- **Skill:** IoU / Sørensen of predicted vs. actual perimeter at +30/+60/+180 min, **assimilation ON vs OFF**.
- **Calibration:** reliability diagram + Brier + CRPS; the 90% region should contain the truth ~90% of the time.
- **Sharpness-given-calibration:** area of the 90% region shrinks as observations accumulate.

**Decision (the "moved-the-needle" metric)**
- On the retrospective fire: **evacuation lead-time delta**, how much earlier FIREWATCH would have flagged the threatened zone at a fixed confidence, vs. the actual timeline / vs. the no-assimilation baseline. This single number is the application's centerpiece.

**Engineering**
- One-command reproducible replay; cycle latency ≤ cadence (NFR-1); all feeds free.

---

## 13. Open questions

- Which retrospective fire(s)? Need good public camera coverage **and** high-quality perimeter time series. Pick during M1 when data availability is known.
- Learned surrogate vs. pure physical prior for FR-FC-1, decide empirically at M4; physical prior first.
- Perimeter-observation matching scheme, evaluate morphing-EnKF-style correction vs. simpler front-distance likelihood.
