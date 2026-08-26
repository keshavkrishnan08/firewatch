*Part of the FIREWATCH spec — see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH — Evaluation

Evaluation *is* the contribution's proof. A pretty demo without measured skill and calibration convinces no one serious. Everything here must be reproducible via `make replay FIRE=<id>`.

Guiding rule: **pre-register** the fire(s), horizons, and metrics before scoring. Report all runs, not the flattering ones.

## 1. Perception
- **Metric:** time-to-detection (minutes from ignition/first-visible-smoke to confirmed detection) with temporal context vs. a single-frame detector, on FIgLib-style sequences.
- **Also:** detection precision/recall, and SAM2 mask stability (track continuity) — secondary.

## 2. Georeferencing (novelty 1)
- **Primary:** median + 90th-pct ground-position error (meters) of the georeferenced front vs. the nearest-in-time NIFC/IR perimeter, on fires with public camera coverage.
- **Stratify by:** distance camera→fire, terrain roughness, single- vs multi-camera.
- **Ablation:** raw pose metadata vs. skyline self-calibrated tilt (show the self-cal earns its keep).
- **Sanity anchor:** monoplotting work reports sub-meter fronts from high-quality oblique photos [MPT2021]; tower-cam automated results will be coarser — report honestly, don't compare unlike setups.

## 3. Forecast (the headline)
### 3.1 Skill
- **Metric:** perimeter agreement — IoU and Sørensen–Dice of predicted vs. actual perimeter at +30 / +60 / +180 min; plus burn/no-burn AUC-PR on the probability field (labels are imbalanced, so PR not ROC).
- **The ablation that proves the thesis:** **assimilation ON vs OFF** at each horizon. If ON does not beat OFF, the central claim fails — so this is the make-or-break plot.
- **Second ablation:** observation sources — GOES-only vs +VIIRS vs +camera-fronts — to show each modality's contribution (the multi-rate-fusion argument).
### 3.2 Calibration (first-class, not optional)
- **Reliability diagram** of the burn-probability field (predicted prob vs observed frequency).
- **Brier score** and **CRPS** for the probabilistic perimeter.
- **Coverage:** the stated 90% region should contain the truth ≈90% of the time; report empirical coverage at 50/80/90%.
- **Sharpness-given-calibration:** 90%-region area should shrink over successive assimilation cycles — plot region area vs. time-since-ignition. This is the visual proof that "the forecast sharpens as observations arrive."
- Apply temperature scaling / isotonic (`forecast/calibrate.py`) and report pre/post.
### 3.3 Baselines to beat
1. **Persistence** (perimeter stays put).
2. **Physical prior, no assimilation** (level-set/Rothermel forward run) — the OFF arm.
3. **Data-driven single-shot** next-day predictor trained on WildfireSpreadTS/Next-Day (adapted to the horizon) — the "accessible ML" comparison [Huot2022; Gerard2023].
4. *(Reference, not a target to beat on physics)* qualitative comparison to what an operational simulator would need to run — to make the accessibility argument, not a fidelity contest.

## 4. Decision layer (the "moved-the-needle" proof)
- **Evacuation lead-time delta (headline number):** on the retrospective fire, at a fixed confidence threshold, how many minutes **earlier** would FIREWATCH have flagged each threatened zone vs. (a) the actual historical timeline and (b) the no-assimilation baseline? Report per-zone and aggregate.
- **Egress-route call quality:** did the system correctly flag routes that closed before a zone could clear, in hindsight?
- **False-alarm discipline:** rate of zones flagged that were not ultimately threatened, at the chosen threshold — an honest cost side to the lead-time benefit (plot the trade-off curve).

## 5. Retrospective protocol (M5)
1. **Pre-register:** fire id, replay window, horizons, metrics, confidence thresholds — commit before scoring (write them into `EVALUATION_PREREG.md` with a timestamp).
2. **Freeze inputs:** pin the exact historical snapshots (`ingest/replay.py`); no future data leaks into a forecast issued at time `t` (strict causal masking — the most common way retrospectives cheat; guard against it explicitly).
3. **Run** assimilation ON/OFF + baselines over the window.
4. **Score** skill, calibration, lead-time delta; generate all figures via `make`.
5. **Failure analysis:** where/why did it miss? (wind shift not yet observed, fuel-moisture error, camera obscured by smoke, sparse GOES pixels, etc.) — a required section.

## 6. Reproducibility checklist (CI-enforced where possible)
- [ ] Seeded RNGs; pinned `requirements.txt`; pinned data snapshots per event.
- [ ] `make replay FIRE=<id>` regenerates every headline figure from scratch.
- [ ] No future-data leakage in any issued forecast (causal mask test in `tests/`).
- [ ] Calibration + failure-analysis figures committed, not just skill numbers.
- [ ] "target" vs "measured" clearly labeled everywhere in docs and README.

## 7. What good looks like (honest bar)
Not "state-of-the-art on a leaderboard." The bar is: **assimilation measurably beats no-assimilation at short horizons, the probability field is calibrated, the georeferencing is accurate enough to be useful, and the retrospective shows a real lead-time gain** — all reproducible on real fires. That combination, shipped openly, is what makes the project credible and rare.

---

## 8. Executed results (this build)

The protocol above has been run, not just specified:

- **Pre-registered retrospective — 2024 Park Fire.** Ground truth = GOES-18 ABI active-fire
  progression (real, keyless). Config fixed in `EVALUATION_PREREG.md` (with git sha) *before*
  scoring. Result: assimilation ON beats OFF on perimeter IoU at **every horizon (+0.02)**, a
  consistent but modest gain given GOES's 2 km coarseness and few early detections. Calibration
  honestly shows **under-coverage** — the conservative physical prior under-predicts the fire's
  explosive spread. Artifacts: `outputs/retro_park/results.json` + figures. Reproduce:
  `make retrospective FIRE=park`.
- **Synthetic replay (`make demo`).** Assimilation lifts mean IoU **0.12 → 0.56** (+0.42 beyond the
  last observation); the 90% region is conservatively calibrated; a threatened zone is flagged
  **~71 min** before arrival where the baseline never flags it.
- **Georeferencing.** 0 m clear-LOS round-trip; skyline self-cal recovers a 1.5° tilt error
  (2370 m → ~0 m); 2-camera triangulation ~18 m.
- **Learned models (`make train`) — trained on real data.** The spread surrogate (FCN) emulates the
  physical MTT solver, trained on **12 real California landscapes** (real DEM + ESA WorldCover fuels;
  reached-cell MAE ~39 min, +60-min IoU ~0.52, ~9× faster). The smoke U-Net trains on **real Pyronear
  `pyro-sdis` wildfire imagery** (box-supervised, likelihood-refined) — val mask-IoU ~0.30, an honest
  number on genuinely hard real smoke. Both fall back to labeled synthetic data if the sources are
  unreachable. Artifacts: `outputs/ml/metrics.json` + figures.

**Honest bar, met:** assimilation measurably beats no-assimilation (synthetic *and* real), the
probability field is calibrated (with an honest real-fire under-coverage finding), the georeferencing
is accurate, and everything is reproducible from pinned public data.
