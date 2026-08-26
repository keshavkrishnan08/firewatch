# Retrospective pre-registration — Park Fire (2024)

*Committed BEFORE scoring (docs/EVALUATION.md §5). Ground truth = GOES-18 ABI active-fire progression.*

- **Fire:** Park Fire (2024)  (key: `park`)
- **Approx. center:** (39.87, -121.68)
- **Replay window (UTC):** 2024-07-24T22:00:00Z + 360 min
- **Assimilation window:** first 180 min (GOES only, strict causal masking)
- **Forecast horizons (min since first detection):** [210, 240, 300, 360]  (all > assimilation window)
- **Skill metrics:** perimeter IoU, Sørensen–Dice, burn Brier score, coverage @50/80/90%
- **Decision metric:** evacuation lead-time delta @ confidence threshold = 0.5
- **Baselines:** assimilation OFF (physical prior, no obs); persistence is implicit (early perimeter)
- **Ensemble:** 40 members, wide wind prior (direction σ=45°) so ON must earn its skill
- **Grid:** 300 m cells, ±26 km; DEM=Terrain Tiles, fuels=ESA WorldCover, wind=HRRR
- **Committed at:** 2026-08-26T00:08:45.057932+00:00  ·  **git sha:** 62e84c7

> No forecast issued at time t uses any observation after t. Results are appended to
> `outputs/retro_park/results.json` and figures under `outputs/retro_park/figures/`.
