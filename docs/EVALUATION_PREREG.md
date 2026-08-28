# Retrospective pre-registration, 5 real fires (GOES-18 era)

*The pinned record is the version-controlled `retrospective.RETRO_REGISTRY` and the git history;
this file is a human-readable snapshot. Ground truth = GOES-18 ABI active-fire progression (real,
keyless). No forecast issued at time t uses any observation after t (strict causal masking); the
scored window is held out beyond the assimilation window.*

## Pre-registered fires

| Fire | key | Approx. center (lat, lon) | Start (UTC) | Window (min) | Assim (min) | Horizons (min) | Grid |
|---|---|---|---|---|---|---|---|
| Park Fire (2024) | `park` | (39.87, -121.68) | 2024-07-24T22:00:00Z | 360 | 180 | [210, 240, 300, 360] | 300 m, ±26 km |
| Palisades Fire (2025) | `palisades` | (34.08, -118.55) | 2025-01-07T18:30:00Z | 360 | 180 | [210, 240, 300, 360] | 250 m, ±16 km |
| Eaton Fire (2025) | `eaton` | (34.19, -118.13) | 2025-01-08T02:30:00Z | 360 | 180 | [210, 240, 300, 360] | 250 m, ±14 km |
| Davis Fire (2024) | `davis` | (39.3053, -119.8325) | 2024-09-07T21:30:00Z | 360 | 180 | [210, 240, 300, 360] | 250 m, ±16 km |
| Gray Fire (2023) | `gray` | (47.54, -117.731) | 2023-08-18T19:27:00Z | 360 | 180 | [210, 240, 300, 360] | 250 m, ±15 km |

## Fixed protocol (same for every fire)

- **Skill:** perimeter IoU, Sørensen-Dice, burn Brier score, per-horizon.
- **Coverage:** empirical coverage of the 90% credible region vs GOES truth, reported **raw** and
  **calibrated**. Calibration = a fast-tail ensemble spread mixture (tight core preserves the p≥0.5
  point forecast) plus **leave-one-out** region-level calibration across fires. Never tuned to the
  fire being scored; both numbers published.
- **Ablation baseline:** assimilation OFF (physical prior, no obs), the ON arm must beat it.
- **Warning lead time:** for each community the fire reaches after forecast issue, the interval
  between the forecast first flagging it and the fire's GOES-observed arrival (non-positive where the
  community is already inside the fire at issue, reported honestly).
- **Reproduce:** `make history` regenerates `outputs/historical.json`, all figures, and the site.

- **Snapshot committed at:** 2026-08-27T14:55:33.977479+00:00  ·  **git sha:** cc57213
