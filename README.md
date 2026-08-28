# 🔥 FIREWATCH

**A real-time wildfire common operating picture: fuse camera + satellite + weather + terrain into
a continuously self-correcting probabilistic spread forecast, and turn it into human-in-the-loop
evacuation and resource decisions, validated by replaying real fires.**

FIREWATCH is deliberately *not* another wildfire detector. Detection is a commodity and just an
input. The contribution is **integration → assimilation → decision**: model the world as an
ontology of fires, sensors, and threatened assets; assimilate live observations into a *calibrated*
forecast; and drive auditable decisions with lead-time and uncertainty.

> **Status: working end-to-end**, on a reproducible offline synthetic replay, on live public data
> for a real active fire, *and* scored against a **pre-registered retrospective on five real historical
> fires** (Park, Palisades, Eaton, Davis, Gray, across California, Nevada and Washington) with
> GOES-observed ground truth. Terrain, fuels (ESA WorldCover / LANDFIRE),
> and wind (HRRR/NWS) are real; the learned spread surrogate and smoke segmenter are **real trained
> torch models** (`make train`). Numbers are labeled *synthetic* vs *real* throughout, honesty over
> hype is a project principle, not a slogan (see `CLAUDE.md`).

> ### ▶ The FIREWATCH instrument
> A single **self-contained interactive page**, [`docs/history.html`](docs/history.html) (`make history`
> regenerates it; serve `docs/` or open it directly), walks the whole system on **five real fires**
> across California, Nevada and Washington:
> **Fires** (annotated satellite + forecast time-lapses) · **How it works** (the eight-stage pipeline) ·
> **Ontology** (one fire as a linked object/link/action graph with a provenance ledger) ·
> **Decision** (the incident-commander brief, verified against ground truth) ·
> **Retrospective** (the causal replay, warning lead time, and calibrated coverage) · **Results**.

### The common operating picture

The COP board (MapLibre + deck.gl), driven entirely by public data through the ontology, Observe
(camera → detector → georeferenced front), Map (assimilated burn-probability bands, 90% region,
observations, threatened zones/roads, camera view-cones), and Decide (ranked evacuations, egress,
staging, exposure, NL query), with a time scrubber over the assimilation window:

![FIREWATCH COP board, synthetic demo](docs/assets/cop_board.png)

And the **same system on a real, currently-active fire**, located via NIFC, real terrain + NWS
wind + OSM assets, forecasting forward from the official perimeter (purple), with real egress routes
flagged by threat:

![FIREWATCH COP board, live real fire](docs/assets/cop_board_timber.png)

---

## Why this is different

Two research communities barely talk to each other:

- **Physics + data assimilation** can continuously correct a fire forecast from observations, but
  it's locked inside HPC-scale coupled atmosphere-fire simulators.
- **Data-driven ML** has accessible open datasets, but its models are single-shot, next-day,
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
5. **Decide**, reconstruct the incident-commander brief at forecast issue (communities ranked by
   projected arrival, with an 80% window and confidence), then **verify it against GOES truth**:
   across the five fires the flag runs at ~**88% precision / 82% recall**, it names the communities
   that go on to burn. Every recommendation is traceable to its evidence, and human-in-the-loop.

## Proof, not vibes

The whole point is measured skill + calibration, reproducibly:

| Metric | What it shows | Status |
|---|---|---|
| **Assimilation ON vs OFF** (perimeter IoU) | the central thesis: obs sharpen the forecast | **synthetic demo:** mean IoU **0.12 → 0.56** (+0.42 beyond last obs) · **five real fires (GOES truth):** **+0.01 to +0.13** mean-IoU gain, positive on every fire (honest, modest, GOES is coarse) |
| **Decision quality** (does it flag the right places?) | the "changes a decision" number | **measured on five real fires (GOES truth):** the reconstructed decision brief flags the communities that actually burn at ~**88% precision / 82% recall**, from a forecast issued ~90 min into the fire, verified per-fire in the **Decision** tab |
| **Calibration** (reliability, Brier, coverage) | probabilities mean what they say | **measured** on demo *and* the real retrospective: raw 90% coverage ~**0.68** (over-confident) → **~0.87** after fast-tail spread widening + leave-one-out region calibration; both reported |
| **Georeferencing** ground error vs perimeter | camera→map is accurate enough to use | **measured:** 0 m clear-LOS round-trip; skyline self-cal cuts a 1.5° tilt error's 2370 m → ~0 m; 2-cam triangulation ~18 m |
| **Learned surrogate & smoke segmenter** | real torch models on **real** data | **measured** (`make train`): surrogate (trained on **12 real CA landscapes**) **reached-cell MAE ~39 min**, **~9× faster** than MTT; smoke U-Net (trained on **real Pyronear imagery**) **val mask-IoU 0.30**, honest on genuinely hard real smoke |
| **Warning lead time** | how much earlier a community is flagged than the fire arrives | **synthetic demo:** ~71 min earlier than baseline · **real fires:** measurable where the fire runs into a community *after* forecast issue (e.g. Palisades' Las Flores **+186 min**, Gray's Silver Lake **+36 min**); near-ignition communities are already burning at issue and are reported honestly as such |

Everything regenerates from pinned inputs with one command:

```bash
make demo                    # fully-offline synthetic event, end-to-end, no keys, no network
make replay FIRE=<event_id>  # reproduce the full picture for a real fire
```

## Results (reproducible synthetic replay, run `make demo`)

*All figures below regenerate from pinned inputs; every synthetic artifact is labeled as such.*

**The thesis, measured, assimilation ON vs OFF** (perimeter IoU vs truth at each horizon), and the
COP preview where the assimilated forecast (red) tracks the truth perimeter (dashed) while the 90%
region (blue) stays appropriately wider:

| Assimilation ablation | Common operating picture (preview) |
|---|---|
| ![ablation](docs/assets/ablation_iou.png) | ![cop map](docs/assets/cop_map.png) |

**Calibration is first-class** (reliability diagram + Brier, pre/post temperature scaling), and the
**forecast sharpens as observations arrive** (90%-region area shrinks, IoU rises with each cycle):

| Calibration / reliability | Sharpening over time |
|---|---|
| ![reliability](docs/assets/reliability.png) | ![sharpening](docs/assets/sharpening.png) |

**Perception → georeference** on a tower-cam frame (detector box + SAM2-style plume mask + smoke-state
readout), and a **live COP on a real active fire** (the "Timber" fire, located via NIFC, real terrain
+ NWS wind, forecast forward from the current perimeter):

| Observe pane (camera) | Live real fire (Timber) |
|---|---|
| ![observe](docs/assets/observe_frame.png) | ![timber](docs/assets/live_timber_cop.png) |

Headline numbers on the synthetic replay: mean perimeter **IoU 0.12 → 0.56** with assimilation
(**+0.42** at horizons beyond the last observation); the 90% region is conservatively calibrated; and
a threatened zone is flagged **~71 min before arrival** where the no-assimilation baseline never
flags it.

### Real-fire retrospective, 2024 Park Fire (pre-registered)

The synthetic numbers show the method's ceiling; this shows its **honest real-world behavior**. On the
2024 Park Fire, with **GOES-18 active-fire progression as ground truth** (real, keyless), terrain from
Terrain Tiles, fuels from ESA WorldCover, and HRRR wind, pre-registered
([`docs/EVALUATION_PREREG.md`](docs/EVALUATION_PREREG.md)) before scoring:

The same COP board, on the real historical fire, GOES hotspots, the assimilated forecast, real
Park-Fire-area roads (Richardson Springs Rd, Cohasset Rd) flagged as egress, and the honest
`+0.02 ΔIoU vs baseline` header stat:

![FIREWATCH COP board, Park Fire retrospective](docs/assets/cop_board_retro.png)

| Assimilation ablation (real GOES truth) | Forecast vs observed fire (dashed = GOES truth) |
|---|---|
| ![retro ablation](docs/assets/retro_ablation.png) | ![retro map](docs/assets/retro_cop_map.png) |

Assimilation beats the no-assimilation baseline on **every fire** (mean-IoU gain **+0.01 to +0.13**
across Park/Palisades/Eaton/Davis/Gray), modest to strong, because GOES is coarse (2 km) and only a
few detections fall in the early assimilation window. The calibration analysis first surfaced
**under-coverage** (a tight ensemble under-predicting explosive spread, truth extending beyond the
forecast); the fix is a **fast-tail spread mixture** plus **leave-one-out region calibration** that
lifts raw 90% coverage from ~0.68 to ~0.87, with the irreducible residual (patchy real perimeters at
2 km) named rather than hidden. That kind of honest analysis is a feature: it points squarely at the
remaining upgrades (finer VIIRS observations via a FIRMS key, better live fuel-moisture). This is what credible looks like
on real data.

### The FIREWATCH instrument, historical fire analysis (`make history`)

A self-contained, dark, dense **scientific analysis tool** (in [`docs/history.html`](docs/history.html),
`make history` regenerates it) that replays **five real historical wildfires** from GOES-18, across
three states for geographic and size diversity: **Park** (California, 2024), **Palisades** and **Eaton**
(California, 2025), **Davis** (Nevada, 2024) and **Gray** (Washington, 2023), all real locations,
coordinates, dates and GOES-observed truth. Tabs:

- **Fires**, the tracking + forecast time-lapses (autoplay) for the flagship fires, each with source
  provenance (GOES-18 ABI-L2-FDCC), plus per-fire impact estimates and the step-by-step evolution stills.
- **How it works**, the eight-stage pipeline, each with a real figure and an input→process→output diagram.
- **Ontology**, one fire rendered as a Palantir-style **object/link/action graph** (feeds → observations
  → fire → forecasts → communities → recommend, with a human-decides gate) plus the **provenance ledger**.
- **Retrospective**, the causal replay: warning lead time community by community, the assimilation
  ablation across all five fires, and **raw vs calibrated 90% coverage**.
- **Results**, the per-horizon skill table (IoU baseline vs assimilation, Dice, Brier, coverage) and
  the measurement graphs; **How it helps** frames the operational use.

The tracker is real multi-object tracking (DBSCAN clustering of GOES fire pixels + nearest-centroid
association); the fires are fused with the assimilating forecast over real terrain (Terrain Tiles),
fuels (ESA WorldCover) and wind (HRRR). Assimilation beats the no-assimilation baseline on **every fire**
(mean perimeter IoU), by **+0.01 to +0.13**, modest to strong, honest, real-data gains (GOES is coarse
at ~2 km). The ensemble's 90% credible region, raw, was over-confident (~0.68 mean coverage); a fast-tail
spread mixture plus **leave-one-out region calibration** lifts it to **~0.87**, with both numbers reported
and the irreducible residual (patchy real perimeters at 2 km) named honestly.

### Learned models (`make train`)

Two **real trained torch models** (MPS/CUDA/CPU), by self-distillation, no external download:

| Learned spread surrogate (emulates the physical solver) | Learned smoke segmenter (U-Net) |
|---|---|
| ![surrogate](docs/assets/surrogate.png) | ![smoke net](docs/assets/smoke_net.png) |

Both models train on **real data** (`make train`). The surrogate emulates the Rothermel+MTT arrival
field in one forward pass, trained on **12 real California landscapes** (real DEM + ESA WorldCover
fuels; only wind/moisture are perturbed), a *fast approximate* prior (**reached-cell MAE ~39 min** over
0-180 min, **+60-min IoU ~0.52**), **~9× faster** than sequential MTT for an ensemble; the assimilation
loop then refines it and stays unchanged. The smoke U-Net trains on **real Pyronear `pyro-sdis`
imagery** (HuggingFace, keyless; box-supervised masks refined by the smoke-likelihood field), **val
mask-IoU 0.30**, an honest number on genuinely hard real smoke (faint plumes, clouds, weak labels). It
replaces the classical fallback on the ML path for real frames; the offline synthetic demo uses
classical CV. WildfireSpreadTS / SmokeyNet weights drop in via the same interface.

These are demo (synthetic) headline numbers where noted, real-fire skill is the retrospective above;
full protocol in [`docs/EVALUATION.md`](docs/EVALUATION.md).

## Architecture (the ontology is the bus)

```
public feeds ─▶ INGEST ─▶┐
 cameras ─▶ PERCEPTION ─▶ ONTOLOGY (versioned source of truth) ─▶ FORECAST ─▶ DECISION ─▶ API ─▶ COP board
                          │  Fire · Perimeter(t) · Observation · Camera · Weather ·        (assimilate)   (evac/routes/
                          │  Terrain · Fuel · Structure · Zone · Road · Recommendation       + calibrate    staging)
```

Modules never exchange raw feed payloads, they read/write ontology objects. Every object is
time-stamped and versioned, so the UI time-scrubber and the retrospective replay are just queries
over object history (and no future data can leak into a past state, a causal-masking guarantee we
test). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/ONTOLOGY.md`](docs/ONTOLOGY.md).

## Milestones (each independently demoable)

- **M1**, Live COP from public feeds *(integration; no ML)*
- **M2**, Perception *(YOLO/RT-DETR + SAM2, classical fallback)*
- **M3**, Georeferencing *(camera plume → lat/lon + uncertainty, novelty 1)*
- **M4**, Assimilating spread forecast *(the research core; ON-vs-OFF ablation + calibration)*
- **M5**, Decision layer + retrospective *(the "moved-the-needle" case study)*

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

- [`CLAUDE.md`](CLAUDE.md), operating manual · [`context.md`](context.md), full consolidated spec
- [`docs/PRD.md`](docs/PRD.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
  [`docs/ONTOLOGY.md`](docs/ONTOLOGY.md) · [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) ·
  [`docs/EVALUATION.md`](docs/EVALUATION.md) · [`docs/REFERENCES.md`](docs/REFERENCES.md)

## License / data

Code: MIT. All data feeds are free/public; respect each source's terms. **FIREWATCH recommends; a
human decides, it never issues autonomous orders.**
