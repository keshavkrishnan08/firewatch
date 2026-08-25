*Part of the FIREWATCH spec — see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH — Data Sources

Every feed is free/public. This is the part that makes the project *buildable and verifiable*. Verify endpoints and terms at build time; treat resolutions/cadences below as planning figures. Access keys go in `.env` (see `.env.example`).

Legend: **O** = live observation for assimilation · **F** = forcing/static layer · **A** = assets · **D** = training/eval dataset · **GT** = retrospective ground truth.

## Observation feeds (drive the assimilation loop)

### NASA FIRMS — active fire (VIIRS 375 m, MODIS 1 km) · **O, GT**
- Near-real-time active-fire detections; area/CSV API with a free MAP_KEY.
- VIIRS (S-NPP/NOAA-20/21) 375 m is the workhorse; a few overpasses/day → spatially good, temporally sparse.
- Use: primary satellite observation for the filter; also historical time series for retrospectives.

### GOES-R ABI Fire Detection & Characterization (FDC) · **O**
- Geostationary (GOES-East/West) → **~5-minute CONUS cadence**; coarse pixels but dense in time.
- Access via AWS S3 open buckets (`goes2go` helper); product level-2 FDC.
- Use: high-cadence observation that keeps the forecast honest between VIIRS passes — the temporal backbone of "the forecast sharpens as observations arrive."

### ALERTCalifornia / ALERTWildfire tower cameras · **O (via perception)**
- 1000+ geo-located PTZ/fixed cameras (CA focus; HPWREN heritage), publicly viewable imagery, ~1 frame/min, archived imagery accessible. Newer cams color+PTZ; some older mono/fixed.
- Camera metadata (lat/lon/elev, orientation) needed for georeferencing; PTZ tilt often approximate → handled by skyline self-calibration (`perception/skyline.py`).
- Use: source frames for detection/segmentation → georeferenced camera-front observations.

### NIFC / WFIGS operational fire perimeters · **O (late), GT**
- Authoritative incident perimeters (IR flights / field mapping), updated intermittently.
- Use: occasional high-quality observation for late assimilation **and** the ground truth that forecast IoU/lead-time metrics are scored against.

## Forcing & static layers (spread inputs)

### NOAA HRRR — hourly high-res weather · **F**
- 3 km CONUS, hourly, includes 10-m wind (u/v), RH, temperature; access via AWS S3 (`Herbie`).
- Use: wind field for ROS + the dominant ensemble-perturbation variable.

### RAWS — Remote Automated Weather Stations · **F**
- Point weather obs; useful to nudge/verify HRRR locally.

### USGS 3DEP / SRTM — digital elevation · **F**
- 1–10 m (3DEP) / 30 m (SRTM) DEM → elevation/slope/aspect.
- Use: ROS slope term **and** the ray-cast surface for georeferencing (`perception/georeference.py`).

### LANDFIRE — fuels & vegetation · **F**
- Fuel models, canopy cover/height, existing vegetation type at 30 m.
- Use: fuel term of Rothermel ROS; fuel moisture is an ensemble-perturbed unknown.

## Assets (decision layer)
### Building footprints — Microsoft Building Footprints / OSM · **A**
### Population — US Census blocks · **A**
### Roads — OpenStreetMap · **A**
- Use: exposure (structures/people over the forecast horizon), egress-route graph + threat timing, safe staging candidates.

## Datasets for training / eval (offline)

| Dataset | Use | Note |
|---|---|---|
| **FIgLib** (+ SmokeyNet) · **D** | smoke detection / time-to-detection | ~25k SoCal HPWREN smoke images, sequence-oriented |
| **FLAME / FLAME2** · **D** | fire/smoke video | ignition-time annotations |
| **AusSmoke / MultiNatSmoke** · **D** | smoke segmentation | diverse, fully labeled masks |
| **Next Day Wildfire Spread** · **D** | spread surrogate pretraining | US, next-day, multi-modal |
| **WildfireSpreadTS** (+ **WSTS+**) · **D** | multi-temporal spread | 13,607 imgs / 607 fires / 23 ch |
| **Mesogeos**, **SeasFire**, **Sim2Real-Fire** · **D** | broader spread substrate | Mediterranean / global / sim2real |
| **MTBS** · **GT** | historical burn perimeters/severity | retrospective ground truth |

## Retrospective case-study selection (M5)
Pick during M1 once availability is confirmed. Requirements for a good replay fire:
1. **Public camera coverage** (ALERTCalifornia) with archived frames spanning early growth.
2. **Frequent, high-quality perimeter time series** (NIFC IR flights) for scoring + lead-time.
3. **Rich GOES/VIIRS active-fire history** over the burn period.
4. Terrain/wind interest (so assimilation visibly matters), and enough documentation to reconstruct the *actual* decision timeline (for the "moved-the-needle" comparison).

Target 1–2 well-documented recent California fires meeting all four. Do **not** hand-pick a fire where the method happens to look good — pre-register the fire and horizons before scoring.

## Access hygiene
- Keys/tokens in `.env` only; `.env.example` lists names, never values. Never commit secrets.
- Respect each source's terms of use and rate limits; cache aggressively per `event_id` under gitignored `data/`.
- Record retrieval time in every Observation's provenance (needed for both assimilation and audit).
