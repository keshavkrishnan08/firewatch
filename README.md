# 🔥 FIREWATCH

**A real-time wildfire common operating picture: fuse camera + satellite + weather + terrain into
a continuously self-correcting probabilistic spread forecast, and turn it into human-in-the-loop
evacuation and resource decisions — validated by replaying real fires.**

FIREWATCH is deliberately *not* another wildfire detector. Detection is a commodity and just an
input. The contribution is **integration → assimilation → decision**: model the world as an
ontology of fires, sensors, and threatened assets; assimilate live observations into a *calibrated*
forecast; and drive auditable decisions with lead-time and uncertainty.

> **Status: early build, working end-to-end on an offline synthetic replay.** Numbers below the
> "measured" heading are from the reproducible synthetic demo (`make demo`) and are labeled as such;
> real-fire numbers are marked **target** until scored on a pre-registered fire (`docs/EVALUATION.md`).
> Honesty over hype is a project principle, not a slogan — see `CLAUDE.md`.

---

## Why this is different

Two research communities barely talk to each other:

- **Physics + data assimilation** can continuously correct a fire forecast from observations — but
  it's locked inside HPC-scale coupled atmosphere–fire simulators.
- **Data-driven ML** has accessible open datasets — but its models are single-shot, next-day,
  offline, and stop at a prediction map with no calibration and no decisions.

FIREWATCH bridges them: **a lightweight, real-time, single-GPU forecaster that assimilates fused
camera + satellite observations into a *calibrated* probabilistic perimeter, wrapped in a decision
layer.** None of the individual pieces are new; the bridge and the operational packaging are. See
[`docs/LITERATURE_REVIEW.md`](docs/LITERATURE_REVIEW.md) for the full, honest gap analysis.

## What it does

1. **Integrate** public feeds (NASA FIRMS, GOES active fire, NOAA HRRR, USGS DEM, LANDFIRE, NIFC
   perimeters, ALERTCalifornia cameras, OSM/Census assets) into one time-versioned **ontology**.
2. **Perceive** smoke/flame on tower cameras (YOLO/RT-DETR + SAM2, with a classical-CV fallback so
   the pipeline runs without a GPU).
3. **Georeference** the camera plume onto terrain → a fire front at **lat/lon + uncertainty cone**,
   with skyline self-calibration for imprecise PTZ tilt *(novelty 1)*.
4. **Forecast** spread with a Rothermel + minimum-travel-time ensemble that **assimilates**
   GOES/VIIRS/camera observations via a regularized particle filter → a calibrated burn-probability
   field at +15/+30/+60/+180 min that **sharpens as observations arrive** *(research core)*.
5. **Decide** — risk-to-population, evacuation lead-time, egress-route threat, staging — every
   recommendation traceable to its evidence, human-in-the-loop.

## Proof, not vibes

The whole point is measured skill + calibration, reproducibly:

| Metric | What it shows | Status |
|---|---|---|
| **Assimilation ON vs OFF** (perimeter IoU) | the central thesis: obs sharpen the forecast | **measured (synthetic demo):** mean IoU **0.12 → 0.56** across horizons; **+0.42** at horizons *beyond* the last observation |
| **Calibration** (reliability, Brier, CRPS, coverage) | probabilities mean what they say | measured on demo; **target** on real fire |
| **Georeferencing** ground error vs perimeter | camera→map is accurate enough to use | **target** |
| **Evacuation lead-time delta** | the "moved-the-needle" number on a real fire | **target** (M5, pre-registered) |

Everything regenerates from pinned inputs with one command:

```bash
make demo                    # fully-offline synthetic event, end-to-end, no keys, no network
make replay FIRE=<event_id>  # reproduce the full picture for a real fire
```

## Architecture (the ontology is the bus)

```
public feeds ─▶ INGEST ─▶┐
 cameras ─▶ PERCEPTION ─▶ ONTOLOGY (versioned source of truth) ─▶ FORECAST ─▶ DECISION ─▶ API ─▶ COP board
                          │  Fire · Perimeter(t) · Observation · Camera · Weather ·        (assimilate)   (evac/routes/
                          │  Terrain · Fuel · Structure · Zone · Road · Recommendation       + calibrate    staging)
```

Modules never exchange raw feed payloads — they read/write ontology objects. Every object is
time-stamped and versioned, so the UI time-scrubber and the retrospective replay are just queries
over object history (and no future data can leak into a past state — a causal-masking guarantee we
test). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/ONTOLOGY.md`](docs/ONTOLOGY.md).

## Milestones (each independently demoable)

- **M1** — Live COP from public feeds *(integration; no ML)*
- **M2** — Perception *(YOLO/RT-DETR + SAM2, classical fallback)*
- **M3** — Georeferencing *(camera plume → lat/lon + uncertainty — novelty 1)*
- **M4** — Assimilating spread forecast *(the research core; ON-vs-OFF ablation + calibration)*
- **M5** — Decision layer + retrospective *(the "moved-the-needle" case study)*

Full criteria in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Quickstart

```bash
git clone <repo> && cd firewatch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core (forecast/decision/georeference run on this alone)
# optional live feeds: pip install -e ".[geo,sat,osm,perception]"
cp .env.example .env             # add a free NASA FIRMS MAP_KEY for VIIRS/MODIS (optional)

make demo                        # build + run the offline synthetic event end-to-end
make api                         # FastAPI backend  → http://localhost:8000
make web                         # COP board (dev)  → http://localhost:5173
make test                        # acceptance + unit tests
```

## Tech

Python 3.11+ (verified on 3.14). numpy/scipy forecast core; shapely/pyproj/rasterio/geopandas
geospatial; goes2go + Herbie for GOES/HRRR from AWS Open Data; DuckDB + GeoParquet ontology store;
FastAPI backend; MapLibre + deck.gl frontend. All data feeds are free/public; single-GPU target.

## Repository

- [`CLAUDE.md`](CLAUDE.md) — operating manual · [`context.md`](context.md) — full consolidated spec
- [`docs/PRD.md`](docs/PRD.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
  [`docs/ONTOLOGY.md`](docs/ONTOLOGY.md) · [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) ·
  [`docs/EVALUATION.md`](docs/EVALUATION.md) · [`docs/REFERENCES.md`](docs/REFERENCES.md)

## License / data

Code: MIT. All data feeds are free/public; respect each source's terms. **FIREWATCH recommends; a
human decides — it never issues autonomous orders.**
