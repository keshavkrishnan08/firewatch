*Part of the FIREWATCH spec, see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH, Roadmap

Five milestones. **Each one ships something you could screen-record in 60 seconds.** Do not build ahead; each milestone de-risks the next. FR ids reference `PRD.md` §5.

## M1, Live COP from public feeds *(integration; no ML)*
**Goal:** prove the integration thesis with zero modeling risk.
**Build:** `ingest/` connectors for FIRMS, GOES-FDC, HRRR, DEM, LANDFIRE, NIFC, camera tiles, assets; `ontology/store.py`; a minimal `api/` + MapLibre board; the time scrubber over object versions; `ingest/replay.py`.
**Demo:** an active/recent fire on a live board, satellite hotspots, wind vector, official perimeter, a live camera tile, threatened footprints, all from public data, scrubbable in time.
**Acceptance:**
- [ ] ≥5 feeds land as ontology objects with provenance (FR-ING-1..3).
- [ ] `make replay FIRE=<id>` reconstructs the board offline (FR-ING-4, NFR-2).
- [ ] A missing feed degrades gracefully (FR-ING-5).

## M2, Perception *(adopt off-the-shelf)*
**Goal:** pixel-accurate smoke/flame on camera streams.
**Build:** `perception/detect.py` (YOLO/RT-DETR), `segment.py` (SAM2), `features.py`.
**Demo:** tower-cam video with detector boxes + SAM2 plume mask + a live smoke-state readout (area, bearing, growth).
**Acceptance:**
- [ ] Detector + SAM2 run at camera cadence and stream masks (FR-PER-1..2).
- [ ] Time-to-detection reported vs. single-frame baseline on FIgLib-style sequences (FR-PER-4).

## M3, Georeferencing *(NOVELTY 1, the killer single-screenshot demo)*
**Goal:** turn "smoke in pixel (x,y)" into "fire at lat/lon ± region."
**Build:** `perception/georeference.py` (DEM ray-cast), `skyline.py` (tilt self-cal), `triangulate.py`.
**Demo:** click a camera → a map pin with an uncertainty cone drops on the terrain; when two cameras see it, the cone tightens.
**Acceptance:**
- [ ] Georeferenced front + uncertainty region emitted as an Observation (FR-GEO-1,2,5).
- [ ] Skyline self-cal improves position error vs. raw metadata (FR-GEO-3), measured.
- [ ] Median ground error reported vs. NIFC perimeter, as a function of distance-to-fire (`EVALUATION.md`).

## M4, Assimilating spread forecast *(RESEARCH CORE, the headline)*
**Goal:** a probabilistic forecast that **visibly sharpens** as observations arrive and beats a no-assimilation baseline.
**Build:** `forecast/spread.py` (Rothermel + level-set/CA), `ensemble.py`, `assimilation.py` (ensemble/particle filter + perimeter-matching + spurious-fire regularization), `calibrate.py`; optional `surrogate.py`.
**Demo:** side-by-side replay, assimilation OFF (drifts) vs ON (tracks reality), with the 90% region shrinking as GOES/VIIRS/camera observations stream in.
**Acceptance:**
- [ ] Burn-probability field at +30/+60/+180 min with expected perimeter + 90% region (FR-FC-4).
- [ ] **Ablation:** assimilation ON > OFF on perimeter IoU at each horizon (FR-FC-6), the thesis.
- [ ] **Calibration:** reliability diagram + Brier/CRPS; 90% region ≈ 90% coverage (`EVALUATION.md`).
- [ ] Cycle latency ≤ observation cadence on one workstation (NFR-1).

## M5, Decision layer + retrospective *("moved the needle")*
**Goal:** turn the forecast into decisions and prove operational value on a real fire.
**Build:** `decision/risk.py`, `evacuation.py`, `routing.py`, `staging.py`; the Decide pane; the retrospective replay harness; (stretch) `api/query.py` NL box.
**Demo:** on a real named fire, FIREWATCH flags the threatened zone with lead-time + confidence **earlier** than the actual timeline / the no-assimilation baseline; egress routes light up by time-to-threat; staging points suggested; ask a plain-English question, get an ontology-cited answer.
**Acceptance:**
- [ ] Risk-to-population, evacuation lead-time, egress threat, staging, all with evidence trails and confidence (FR-DEC-1..5).
- [ ] **Retrospective:** evacuation lead-time delta quantified on ≥1 pre-registered real fire (`PRD.md` §12), the application centerpiece.
- [ ] Full reproducible replay + calibration + honest failure analysis in the repo.

## Sequencing / dependencies
M1 → (M2 → M3) → M4 → M5. M2/M3 (camera track) and the satellite/forecast track (M1→M4) can partly parallelize, but M4 needs M1's observation plumbing and benefits from M3's camera fronts.

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Imprecise PTZ pose metadata | High | Med | Skyline-to-DEM tilt self-cal (FR-GEO-3); bearing-only fallback; multi-cam triangulation |
| EnKF spurious fires / instability | Med | High | Tikhonov regularization; morphing/matching front operator; particle-filter fallback; cap spread [Mandel2009; Beezley2008] |
| Sparse observations on chosen fire | Med | Med | Lean on GOES 5-min cadence; widen uncertainty honestly; pick fire with good coverage (M1) |
| Forecast worse than baseline at some horizon | Med | Med | Report it, honest failure analysis is a feature; investigate regimes where assimilation helps most |
| Scope creep (3D/VLM/domain-adapt) | High | High | Milestone gates; stretch items fenced in PRD §3.2; NL query is read-only, last |
| Overclaiming novelty | Med | High | Gap analysis states prior art plainly (`LITERATURE_REVIEW.md` §7, §9) |
| Retrospective looks cherry-picked | Med | High | Pre-register fire + horizons before scoring; report all runs, not the best |

## Definition of done (project)
A public, reproducible repo where `make replay FIRE=<id>` reproduces: the live COP, the georeferenced camera fronts, the assimilation ON/OFF ablation, the calibration diagrams, and the retrospective lead-time delta, plus a short writeup and a 2-3 minute demo video. That package is the fellowship artifact.
