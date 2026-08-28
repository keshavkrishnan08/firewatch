# 🔥 FIREWATCH, Master Specification

**A real-time wildfire common operating picture: fuse camera + satellite + weather + terrain into a
continuously self-correcting probabilistic spread forecast, and turn it into human-in-the-loop
evacuation and resource decisions, validated by replaying real fires.**

*Consolidated single-document spec · v1.0 · 2026 August 25.*
*This file is the entire FIREWATCH context set (working manual, PRD, literature review,
architecture, ontology, data sources, roadmap, evaluation, references) plus the code scaffold in
one self-contained document. Positioning: **integration → assimilation → decision**, not "another
wildfire detector."*

> This `context.md` is the single-file master. `CLAUDE.md` is the operating manual (Part 0) and the
> `docs/` tree is the authoritative split (Parts 1-8). If you only read one file, read `CLAUDE.md`,
> then `docs/PRD.md`.

---

## Contents

0. Part 0, Working Context (operating manual)
1. Part 1, Product Requirements (PRD)
2. Part 2, Literature Review & Gap Analysis
3. Part 3, Architecture
4. Part 4, Ontology (objects · links · actions)
5. Part 5, Data Sources
6. Part 6, Roadmap
7. Part 7, Evaluation
8. Part 8, References
9. Appendix, Repository layout & scaffold sources

---

<a id="part-0"></a>

## Part 0, Working Context (operating manual)

> Read this first. This file is the operating manual for anyone (human or Claude Code)
> working in this repo. If you only read one file, read this one, then open `docs/PRD.md`.

### What FIREWATCH is (one paragraph)

FIREWATCH is a real-time **wildfire common operating picture (COP)**: an open-source system
that ingests heterogeneous public feeds, ground/tower camera imagery, geostationary and
polar-orbiting satellite active-fire products, weather, terrain, and fuels, resolves them into
a single **ontology** of fires, sensors, and threatened assets, produces a **probabilistic
short-horizon spread forecast that continuously self-corrects as new observations arrive**
(data assimilation), and drives a **human-in-the-loop decision layer** (evacuation lead-time,
egress-route threat, resource pre-positioning) with calibrated uncertainty. It is deliberately
*not* "another wildfire detector." Detection is a solved commodity; the contribution is
**integration + assimilation + decision support**, delivered as verifiable open software and
validated by retrospective replay of real, named historical fires.

The design target is the DNA of Palantir Foundry/AIP: bring the right data to the people making
the decision, model the world as objects/links/actions, keep the human in the loop, and prove it
against reality.

### Why it is built this way (the thesis)

Two research communities barely talk to each other:

1. **Physics + data assimilation** (Mandel, Rochoux & Trouvé, WRF-SFIRE): mature methods for
   correcting a running fire simulation with incoming observations, but locked inside
   heavyweight coupled atmosphere-fire simulators that need HPC and expert operation.
2. **Data-driven ML forecasting** (Next Day Wildfire Spread, WildfireSpreadTS, Mesogeos):
   accessible, open datasets and models, but almost all are **single-shot, next-day, offline**
   predictors with no notion of continuously assimilating live observations, no calibrated
   uncertainty, and no decision layer.

FIREWATCH's wedge is the bridge: **a lightweight, real-time, observation-assimilating
probabilistic spread forecaster that fuses camera + satellite observations and is wrapped in an
operational decision interface.** See `docs/LITERATURE_REVIEW.md` §7 (Gap Analysis) for the
defensible-novelty argument, and be honest about prior art, do not claim assimilation is new;
claim the *accessible, real-time, fused, open, decision-oriented* packaging of it is the gap.

### Build order (do NOT build it all at once)

Ship a working, demoable slice at every milestone. Full detail in `docs/ROADMAP.md`.

- **M1, Live COP from public feeds.** Ingest FIRMS/VIIRS + GOES hotspots + HRRR wind + a
  camera tile onto a map. No ML yet. Deliverable: a live board of a currently- or
  recently-burning fire. This alone already looks like Foundry.
- **M2, Perception.** YOLO/RT-DETR smoke+flame detection → SAM2 plume masks on camera frames.
  Deliverable: pixel-accurate smoke masks streamed on tower-camera video.
- **M3, Georeferencing (first novelty).** Project the smoke plume onto a DEM to output a
  **lat/lon** + uncertainty cone for the ignition/front. Deliverable: "click a camera, get a
  map pin." This is the killer single-screenshot demo.
- **M4, Assimilating spread forecast (core research).** Cellular-automaton/level-set spread
  model + ensemble/particle assimilation of GOES/VIIRS/camera observations → probabilistic
  perimeter at +30/+60/+180 min with calibration. Deliverable: a forecast that visibly
  sharpens as observations stream in, beating a no-assimilation baseline.
- **M5, Decision layer + retrospective.** Risk-to-population, evacuation lead-time, egress
  threat, staging suggestions; then replay a real named fire and show earlier/better warning.
  Deliverable: the "moved the needle" case study + NL query flourish.

### Working principles (apply these on every task)

1. **Honesty over hype.** Every claim in docs must be checkable. If a number isn't measured
   yet, say "target," not "achieved." Calibration and failure analysis are features.
2. **Real data only.** No synthetic-only results in headline claims. If you must simulate,
   label it. Prefer replaying real historical fires with known perimeters.
3. **Everything is reproducible.** A fixed fire event + `make replay FIRE=<id>` regenerates any
   figure. Seed RNGs. Pin data snapshots.
4. **Uncertainty is first-class.** No point forecasts in the decision layer, always a
   distribution or probability field, always calibrated.
5. **The ontology is the source of truth.** Modules never pass raw feed payloads to each
   other; they read/write ontology objects.
6. **Human-in-the-loop, never autonomous action.** The system *recommends*; a human decides.
7. **Small, shippable, demoable.** Prefer a thin end-to-end slice over a deep half-built subsystem.

### Tech stack (defaults)

- **Language:** Python 3.11+ (verified on 3.14).
- **Geospatial:** `rasterio`, `rioxarray`, `xarray`, `geopandas`, `shapely`, `pyproj`, `pystac-client`.
- **Perception:** `ultralytics` (YOLO) or `transformers` RT-DETR; `sam2` (Segment Anything 2). Optional; classical-CV fallback ships in-repo.
- **Numerics/assimilation:** `numpy`, `scipy`, `numba` (CA kernel); ensemble/particle filter in-repo.
- **Weather/satellite access:** NASA FIRMS API; NOAA HRRR via AWS S3 (`Herbie`); GOES ABI via AWS S3 (`goes2go`); DEM via USGS 3DEP / SRTM; fuels via LANDFIRE.
- **Serving/UI:** FastAPI backend; `deck.gl` + MapLibre frontend (COP board).
- **Reproducibility:** `make` targets, pinned `requirements.txt`, event-snapshot caching.

### Conventions

- One connector per feed under `ingest/`, each exposing `fetch(bbox, time_window) -> Observation`.
- All timestamps UTC, ISO-8601. Geometry EPSG:4326 for storage, projected CRS for math.
- Every observation carries a **provenance** field, required for assimilation weighting and audit.
- Do not commit large rasters; cache under `data/` (gitignored) keyed by event id.
- Tests: each milestone has an acceptance test in `tests/` mirroring the ROADMAP criteria.

### Guardrails / scope discipline

- **In scope:** integration, georeferencing, assimilation, calibrated forecast, decision support, retrospective validation, open reproducibility.
- **Stretch only (clearly labeled):** 3D digital twin, cross-region domain-adaptation as a marquee result, chat/VLM layer. NL query is a thin read-only convenience.
- **Never** present the system as issuing autonomous evacuation orders. It informs a human.

### For the application (why this exists)

Flagship portfolio piece for the **Palantir Meritocracy / American Tech Fellowship**. Optimize for:
a live demo on real data, a public reproducible repo, honest evaluation, and a retrospective on a
real fire.

---

*(Parts 1-8 and the Appendix follow the split in the `docs/` tree; see `docs/PRD.md`,
`docs/LITERATURE_REVIEW.md`, `docs/ARCHITECTURE.md`, `docs/ONTOLOGY.md`, `docs/DATA_SOURCES.md`,
`docs/ROADMAP.md`, `docs/EVALUATION.md`, `docs/REFERENCES.md`. This master file intentionally keeps
Part 0 in full; the remaining parts are maintained as the authoritative standalone docs to avoid
drift.)*
