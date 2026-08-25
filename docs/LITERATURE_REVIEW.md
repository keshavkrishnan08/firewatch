*Part of the FIREWATCH spec — see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md). Full citations in [`REFERENCES.md`](REFERENCES.md).*

# FIREWATCH — Literature Review & Gap Analysis

**Purpose:** establish what exists, what works, and precisely where the open gap is — so the novelty claims in `PRD.md` are defensible and *honest*. Full citations in `REFERENCES.md`. Where a claim rests on a specific source, the short key (e.g., [Mandel2009]) points there.

> **Reviewer-honesty rule:** none of the components below are individually new. Detection, segmentation, spread simulation, and data assimilation all have deep literatures. FIREWATCH's contribution is the **bridge and the packaging** (§7). Say so plainly; it reads as maturity.

## 1. Video fire & smoke detection (mature — commodity)

A large body of work detects flame/smoke in imagery and video; a 2024 review surveys ~150 video-fire papers under a unified taxonomy and catalogs ~17 public datasets, explicitly flagging **limited realistic data, robustness, and generalization** as the persistent weaknesses rather than raw accuracy [Gaur2024/Review]. Purpose-built sequence models exist: **SmokeyNet**, trained on the **FIgLib** archive (~25k labeled wildfire-smoke images from Southern California HPWREN towers), targets real-time smoke detection from image *sequences* [Dewangan2022]. Video fire benchmarks such as **FLAME/FLAME2** and newer smoke-segmentation sets (**AusSmoke/MultiNatSmoke**) add ignition-time and pixel annotations [Shamsoshoara2021].

**Takeaway for FIREWATCH:** detection is a solved commodity and an *input*, not a contribution. Use off-the-shelf YOLO/RT-DETR + SAM2; the only detection-side experiment worth reporting is **time-to-detection** with temporal context vs. a single-frame baseline.

## 2. Promptable video segmentation (mature — adopt directly)

**SAM 2** extends Segment Anything to video with a streaming memory that propagates object masks across frames, released with the large SA-V video dataset [Ravi2024/SAM2]. This is exactly the tool for turning a detector box into a persistent, pixel-accurate plume/flame mask over a tower-camera stream. **Adopt as-is;** no research needed here.

## 3. Satellite active-fire observation (the assimilation fuel)

Operational active-fire products give the observations a forecast can be corrected against:

- **MODIS** (MOD14, 1 km) and **VIIRS** (375 m, VNP14IMG) thermal-anomaly/active-fire products, distributed near-real-time via **NASA FIRMS** [Giglio/Schroeder].
- **GOES-R series ABI** Fire Detection & Characterization (FDC) — *geostationary*, so ~5-minute CONUS cadence: coarse spatially but temporally dense, ideal for a live assimilation loop.

**Takeaway:** the combination of GOES cadence (time) + VIIRS resolution (space) + camera-derived fronts (local precision) is a genuinely multi-rate observation stream — richer than what most data-driven spread models ingest.

## 4. Fire-spread modeling (physics — the transparent prior)

- **Rothermel (1972)** surface rate-of-spread underpins operational tools; **FARSITE/FlamMap** (Finney) propagate perimeters; **ELMFIRE** and **WRF-SFIRE/WRF-Fire** (level-set fire coupled to WRF atmosphere) are the modern simulators [Coen2013; Mandel2011/WRF-SFIRE].
- These are physically faithful but **heavyweight**: HPC, expert setup, not real-time on a laptop, not designed to continuously ingest live heterogeneous observations.

**Takeaway:** use a *lightweight* Rothermel-driven level-set/CA front as a transparent, debuggable prior; do **not** try to out-physics WRF-SFIRE. The value is real-time assimilation + calibration + decisions, not physical fidelity.

## 5. Data-driven spread forecasting (accessible — but single-shot & offline)

A recent, accessible line of work frames spread as image-to-image next-day prediction with open datasets:

- **Next Day Wildfire Spread** — a curated US dataset (fire + weather + terrain + vegetation + population) for predicting next-day active fire from remote sensing [Huot2022].
- **WildfireSpreadTS** — a *multi-temporal* multi-modal dataset (13,607 images, 607 US fire events, 2018–2021, 23 channels, VIIRS active-fire labels) enabling time-series modeling of spread [Gerard2023]; extended by **WSTS+** [Lahrichi2025].
- **Mesogeos** (Mediterranean) and **SeasFire** (global, seasonal) broaden the modeling substrate [Kondylatos2023; Karasante2025]; **Sim2Real-Fire** adds simulation-to-real forecasting [Li2024].

**Critique (this is the opening):** these are overwhelmingly **single-shot, fixed-horizon (next-day), offline** predictors. They do **not** continuously assimilate live observations as a fire evolves, rarely produce **calibrated** probabilistic perimeters, and stop at a prediction map — **no decision layer, no operational loop.**

## 6. Data assimilation for wildfire (powerful — but trapped in simulators)

Correcting a running fire forecast from incoming observations is a real, developed field:

- **Mandel et al.** formulate a wildfire model with **ensemble Kalman filter (EnKF)** assimilation, able to correct even a badly-placed ignition to track observed temperatures [Mandel2008]; the **IEEE Control Systems Magazine** treatment couples EnKF to atmosphere–surface models [Mandel2009]. Statistical perturbations can create **spurious fires**, mitigated by Tikhonov regularization and the **morphing EnKF** (amplitude + displacement correction) [Beezley2008].
- **Rochoux & Trouvé et al.** develop EnKF-based spread data assimilation as a mainstream correction approach [Rochoux2014]; EnKF has also been bolted onto **FARSITE** for perimeter + fuel-adjustment assimilation.
- Mandel et al. later **assimilate satellite active-fire detections** into the coupled weather-fire model [Mandel2016] — conceptually the closest prior art to FIREWATCH's satellite loop.

**Critique (the second half of the opening):** this power lives almost entirely inside **coupled atmosphere–fire simulators requiring HPC and expertise.** It is essentially absent from the accessible, open-source, laptop-scale, camera-fused, decision-oriented tooling world that the §5 datasets inhabit. The two communities barely cite each other.

### 6b. Camera-to-map georeferencing (niche — real, with open prior art to exceed)

Turning an oblique fire/smoke image into ground coordinates is established but under-productized:

- **Ray-tracing against a DEM** to georeference aerial fire-front images, with a bearings-range **EKF** for real-time filtering [Santana2022]; UAV thermal-hotspot geolocation via DEM ray-tracing on complex terrain [rs17233911].
- Photogrammetric **monoplotting** (WSL Monoplotting Tool) georeferences oblique aerial wildfire photos to sub-meter front positions and even recovers **rate-of-spread** [MPT2021].
- Open source: **Pyronear `smoke-localization`** projects a *manually clicked* pixel from a fixed wildfire camera onto terrain to return GPS coordinates — approximate tilt handled crudely.

**Critique / the wedge:** existing camera-geolocation is mostly UAV/aerial (known pose) or requires a human click and approximate tilt. FIREWATCH's step beyond: **automated plume-mask → terrain-intersected front + uncertainty region**, with **skyline-to-DEM tilt self-calibration** for imprecise PTZ metadata and **multi-camera triangulation**, emitted as an assimilation observation. That specific, useful capability is not packaged anywhere open.

### 6c. Uncertainty calibration (borrow directly)

Modern neural predictors are miscalibrated by default [Guo2017]; standard tooling — reliability diagrams, temperature scaling, Brier/CRPS, proper scoring — transfers directly to the burn-probability field. Calibration is treated as a first-class deliverable (`EVALUATION.md`).

### 6d. Operational context (what industry already validates)

Commercial "multi-source ignition detection" (e.g., AEM Elements 360 / MSID) already fuses camera + lightning + satellite + weather into one situational picture — evidence the *integration* thesis is correct and valued operationally. FIREWATCH's differentiation vs. these closed products: **open + reproducible + forward-looking probabilistic forecast with assimilation + an explicit, auditable decision layer**, rather than detection/alerting alone.

## 7. Gap analysis → the FIREWATCH contribution

| Capability | Detection lit (§1–2) | Data-driven forecasting (§5) | DA in simulators (§6) | Camera geo (§6b) | **FIREWATCH** |
|---|---|---|---|---|---|
| Real-time / live loop | partial | ✗ (offline, next-day) | ✓ (but HPC) | partial | **✓ laptop-scale** |
| Continuous observation assimilation | ✗ | ✗ | ✓ | ✗ | **✓** |
| Camera + satellite fused observations | ✗ | ✗ | rare (sat only) | camera only | **✓ both** |
| Calibrated probabilistic perimeter | ✗ | rare | partial | ✗ | **✓ first-class** |
| Automated camera→map front + uncertainty | ✗ | ✗ | ✗ | manual click | **✓ auto + self-cal** |
| Decision layer (evac/routes/staging) | ✗ | ✗ | ✗ | ✗ | **✓** |
| Open, reproducible, single-GPU | mixed | ✓ | ✗ | partial | **✓** |
| Ontology / integration spine | ✗ | ✗ | ✗ | ✗ | **✓ (Foundry-like)** |

**The claim, stated conservatively:** FIREWATCH does not invent detection, segmentation, spread simulation, or data assimilation. It is, to our knowledge, the first **open, real-time, single-GPU system that (a) assimilates fused camera + satellite observations into a calibrated probabilistic spread forecast and (b) turns that forecast into an auditable, human-in-the-loop decision layer,** validated by retrospective replay of real fires. Each half exists in isolation in a different community; the bridge and the operational packaging are the novelty.

**Two concrete, publishable sub-contributions:**

1. **Automated camera-front georeferencing with skyline self-calibration and uncertainty**, as an assimilation observation source (extends §6b beyond manual-click / known-pose UAV cases).
2. **Multi-rate assimilation** (GOES 5-min + VIIRS passes + camera fronts) into a lightweight spread ensemble, with a calibration study showing forecast sharpening over time.

## 8. Datasets to actually use (pointers → `DATA_SOURCES.md`)

- **Detection/segmentation:** FIgLib (+SmokeyNet), FLAME/FLAME2, AusSmoke/MultiNatSmoke.
- **Spread modeling / surrogate pretraining:** Next Day Wildfire Spread, WildfireSpreadTS (+WSTS+), Mesogeos, SeasFire.
- **Retrospective ground truth:** NIFC/WFIGS operational perimeters, MTBS burn-severity perimeters, GOES/VIIRS active-fire time series.
- **Live observation feeds:** FIRMS, GOES ABI FDC, NOAA HRRR, ALERTCalifornia/ALERTWildfire cameras.

## 9. Threats to the contribution (be ready to answer)

- *"This is just plumbing."* → The georeferencing self-calibration and the multi-rate assimilation calibration study are genuine methods results; the plumbing (ontology + decision layer) is the Palantir-relevant systems contribution. Both are defended by measured metrics, not adjectives.
- *"WRF-SFIRE already assimilates satellite fire."* → Yes [Mandel2016]; the difference is accessibility (single GPU, open, real-time), fused camera observations, calibration as a deliverable, and the decision layer. Cite them as the anchor, not as a competitor to beat on physics.
- *"Camera geolocation exists."* → Yes, for UAVs/known pose and manual-click open tools; the automated mask→front + skyline self-cal + uncertainty + multi-cam triangulation packaging is the delta.
