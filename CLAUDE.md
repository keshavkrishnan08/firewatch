# CLAUDE.md — FIREWATCH working context (operating manual)

> Read this first. This is the operating manual for anyone (human or Claude Code) working in this
> repo. If you only read one file, read this one, then open `docs/PRD.md`. The full consolidated
> spec is `context.md`.

## What FIREWATCH is (one paragraph)

FIREWATCH is a real-time **wildfire common operating picture (COP)**: an open-source system that
ingests heterogeneous public feeds — ground/tower camera imagery, geostationary and polar-orbiting
satellite active-fire products, weather, terrain, and fuels — resolves them into a single
**ontology** of fires, sensors, and threatened assets, produces a **probabilistic short-horizon
spread forecast that continuously self-corrects as new observations arrive** (data assimilation),
and drives a **human-in-the-loop decision layer** (evacuation lead-time, egress-route threat,
resource pre-positioning) with calibrated uncertainty. It is deliberately *not* "another wildfire
detector." Detection is a solved commodity; the contribution is **integration + assimilation +
decision support**, delivered as verifiable open software and validated by retrospective replay of
real, named historical fires.

## The thesis (why it's built this way)

Two research communities barely talk to each other: (1) **physics + data assimilation** (Mandel,
Rochoux & Trouvé, WRF-SFIRE) can correct a running fire forecast from live observations but is
locked inside HPC-scale coupled simulators; (2) **data-driven ML forecasting** (Next Day Wildfire
Spread, WildfireSpreadTS, Mesogeos) is accessible but single-shot, next-day, offline, uncalibrated,
and decision-less. FIREWATCH bridges them: a **lightweight, real-time, observation-assimilating,
calibrated** probabilistic spread forecaster that fuses camera + satellite observations, wrapped in
an operational decision interface. See `docs/LITERATURE_REVIEW.md` §7 for the honest gap analysis.

## Repository map

```
firewatch/
├── CLAUDE.md                  ← you are here (operating manual)
├── context.md                 ← full consolidated master spec (single file)
├── README.md                  ← portfolio-facing overview
├── docs/
│   ├── PRD.md                 ← requirements, ontology, FRs/NFRs, metrics
│   ├── LITERATURE_REVIEW.md   ← lit analysis + gap analysis (justifies novelty)
│   ├── ARCHITECTURE.md        ← components, data flow, module boundaries
│   ├── ONTOLOGY.md            ← the object/link/action model (Palantir-style)
│   ├── DATA_SOURCES.md        ← every public feed/API, access notes, gotchas
│   ├── ROADMAP.md             ← 5 milestones, each independently demoable
│   ├── EVALUATION.md          ← baselines, metrics, calibration, retrospective protocol
│   ├── EVALUATION_PREREG.md   ← pre-registration form (fill BEFORE scoring)
│   └── REFERENCES.md          ← verified bibliography
├── src/firewatch/
│   ├── ingest/                ← one connector per feed (FIRMS, GOES, HRRR, cameras, perimeters)
│   ├── perception/            ← detector + SAM2 + camera→map georeferencing
│   ├── ontology/              ← objects, links, actions; the single source of truth
│   ├── forecast/              ← spread model + assimilation loop + uncertainty
│   ├── decision/              ← risk map, evacuation lead-time, egress routing, staging
│   └── api/                   ← FastAPI serving layer + reproducible replay entrypoint
├── web/                       ← MapLibre + deck.gl COP board (three panes + time scrubber)
├── tests/                     ← acceptance tests mirroring ROADMAP criteria
├── scripts/                   ← demo builder, figure generation, retrospective harness
├── pyproject.toml · requirements.txt · Makefile · .env.example · .gitignore
```

## Build order (do NOT build it all at once)

- **M1 — Live COP from public feeds.** Ingest FIRMS/VIIRS + GOES hotspots + HRRR wind + camera tile
  onto a map. No ML yet. Deliverable: a live board of a real fire.
- **M2 — Perception.** YOLO/RT-DETR smoke+flame detection → SAM2 plume masks. (Classical-CV fallback
  ships so the pipeline runs without GPU/model weights.)
- **M3 — Georeferencing (novelty 1).** Project the smoke plume onto a DEM → lat/lon + uncertainty
  cone for the front. "Click a camera, get a map pin."
- **M4 — Assimilating spread forecast (research core).** CA/level-set spread + ensemble/particle
  assimilation of GOES/VIIRS/camera obs → calibrated probabilistic perimeter at +30/+60/+180 min.
- **M5 — Decision layer + retrospective.** Risk-to-population, evacuation lead-time, egress threat,
  staging; then replay a real named fire and show earlier/better warning.

## Working principles (apply on every task)

1. **Honesty over hype.** Every claim must be checkable. "target" vs "measured" is labeled everywhere.
2. **Real data only** in headline claims. Simulated data is labeled as such.
3. **Everything is reproducible.** `make replay FIRE=<id>` regenerates any figure; RNGs seeded; snapshots pinned.
4. **Uncertainty is first-class.** No point forecasts in the decision layer.
5. **The ontology is the source of truth.** Modules exchange ontology objects, never raw payloads.
6. **Human-in-the-loop, never autonomous action.** The system recommends; a human decides.
7. **Small, shippable, demoable.** A thin end-to-end slice beats a deep half-built subsystem.

## Conventions

- One connector per feed under `ingest/`, each exposing `fetch(bbox, t0, t1) -> list[Observation | Layer]`.
- All timestamps UTC, ISO-8601. Geometry stored EPSG:4326; math in a projected CRS.
- Every `Observation` carries **provenance** {source, product, retrieved_at, native_resolution,
  reported_uncertainty} — required downstream.
- Do not commit large rasters; cache under `data/` (gitignored) keyed by `event_id`.
- Every milestone has an acceptance test in `tests/`.

## Guardrails / scope discipline

- **In scope:** integration, georeferencing, assimilation, calibrated forecast, decision support,
  retrospective validation, open reproducibility.
- **Stretch only (labeled):** 3D twin, cross-region domain adaptation as a marquee result, chat/VLM.
  The NL query layer is a thin read-only convenience over the ontology, added last.
- **Never** present the system as issuing autonomous evacuation orders.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # core; add ,geo,sat,osm,perception for live feeds
make demo                          # fully-offline synthetic event, end-to-end, no keys
make replay FIRE=<event_id>        # reproduce the full picture for a real fire
make api                           # FastAPI backend at :8000
make web                           # COP board at :5173
```

## For the application (why this exists)

Flagship portfolio piece for the **Palantir Meritocracy / American Tech Fellowship**. The load-bearing
parts are the M5 retrospective and the success metrics in `docs/PRD.md` §12 — not the model
architecture. Optimize for a live demo on real data, a public reproducible repo, honest evaluation,
and a retrospective on a real fire.
