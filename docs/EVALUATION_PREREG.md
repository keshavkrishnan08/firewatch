# Retrospective pre-registration (fill BEFORE scoring)

Commit this with a timestamp before running any retrospective scoring (EVALUATION.md §5).

- Fire id / name:
- Replay window (UTC start -> end):
- Forecast horizons: +30 / +60 / +180 min
- Skill metrics: perimeter IoU, Dice, burn/no-burn AUC-PR
- Calibration: reliability diagram, Brier, CRPS, coverage @50/80/90%
- Decision metric: evacuation lead-time delta @ confidence threshold = ___
- Baselines: persistence; physical-prior-no-assimilation (OFF arm); data-driven next-day
- Committed at (timestamp / git sha):
