"""Reproducible offline replay entrypoint: `python -m firewatch.api.replay --fire <id>`.

Regenerates the live COP state, georeferenced fronts, the assimilation ON/OFF ablation, calibration
diagrams, the sharpening curve, and the retrospective lead-time delta from pinned inputs. For
`--fire demo` everything is synthetic and offline (no keys / no network). For a real event id it
builds the bundle from the ingest connectors (`firewatch.ingest.replay.build_event`). No future data
leaks into any forecast issued at time t (causal masking is enforced in the forecast engine).
"""
from __future__ import annotations

import argparse
import warnings
from datetime import timedelta

from firewatch.config import EventPaths
from firewatch.forecast.ensemble import EnsembleConfig
from firewatch.ontology.store import Store
from firewatch.pipeline import lead_time_analysis, run_pipeline, sharpening_series
from firewatch.report import generate_figures


def build_bundle(fire: str, store: Store):
    if fire == "demo":
        from firewatch.demo import build_demo_event

        return build_demo_event(store, event_id=fire)
    # real event
    from firewatch.ingest.replay import build_event

    return build_event(fire, store)


def run_replay(fire: str = "demo", n_members: int = 60, quiet: bool = False) -> dict:
    warnings.simplefilter("ignore")
    paths = EventPaths(fire).ensure()
    # fresh ontology db per replay for determinism
    if paths.ontology_db.exists():
        paths.ontology_db.unlink()
    store = Store(paths.ontology_db)
    bundle = build_bundle(fire, store)

    cfg = EnsembleConfig(n_members=n_members)
    has_truth = bundle.truth_arrival is not None
    # demo: issue after the last synthetic obs so the ablation is meaningful; live fire: forecast from now
    issue = bundle.ignition_time + timedelta(minutes=90) if has_truth else bundle.ignition_time
    result = run_pipeline(bundle, issue, ensemble_config=cfg)

    sharp, leads = None, []
    if has_truth:  # the sharpening + lead-time-delta analyses need a truth reference (demo / retrospective)
        sharp = sharpening_series(bundle, [15, 30, 45, 60, 75, 90], horizon=60, cfg=EnsembleConfig(n_members=40))
        leads = lead_time_analysis(bundle, [10, 20, 30, 45, 60, 75, 90], horizon=120, cfg=EnsembleConfig(n_members=40))
    figs = generate_figures(bundle, result, sharp)

    summary = {
        "fire": fire,
        "cop_path": result.get("cop_path"),
        "figures": figs["figures"],
        "metrics": figs["metrics"],
        "lead_time": leads,
        "n_evac": len(result["evacuations"]),
        "n_egress": len(result["egress"]),
        "n_staging": len(result["staging"]),
        "ontology_objects": store.count(),
        "feeds": sorted({o.provenance.source for o in bundle.observations}),
    }
    if not quiet:
        _print_summary(bundle, result, summary)
    store.close()
    return summary


def _print_summary(bundle, result, summary) -> None:
    print(f"\n{'='*74}\n🔥 FIREWATCH replay, {summary['fire']}\n{'='*74}")
    print(f"note: {bundle.note}\n")
    print(f"ontology: {summary['ontology_objects']} object-versions | feeds: {', '.join(summary['feeds'])}")
    if "skill_on" in result:
        so, sf = result["skill_on"], result["skill_off"]
        print("\nAssimilation ablation (perimeter IoU vs truth):")
        print(f"  {'horizon':>8} {'OFF':>7} {'ON':>7} {'delta':>7}")
        for h in result["forecast_on"].horizons:
            print(f"  {'+'+str(h)+'m':>8} {sf[h]['iou']:>7.3f} {so[h]['iou']:>7.3f} {so[h]['iou']-sf[h]['iou']:>+7.3f}")
    cal = summary["metrics"].get("calibration")
    if cal:
        print(f"\nCalibration @ +{cal['horizon']}m: Brier {cal['brier_raw']:.3f} -> {cal['brier_calibrated']:.3f} "
              f"(T={cal['temperature']:.2f}); ECE {cal['ece_raw']:.3f} -> {cal['ece_calibrated']:.3f}")
        cov = cal["coverage"]
        print(f"  coverage @50/80/90%: {cov.get(0.5, float('nan')):.2f} / {cov.get(0.8, float('nan')):.2f} / {cov.get(0.9, float('nan')):.2f}")
    print("\nDecision layer:")
    for r in result["evacuations"][:4]:
        lt = f"{r.lead_time_min:.0f}m" if r.lead_time_min is not None else "n/a"
        print(f"  EVAC  {r.target_name:<16} urgency {r.urgency:.2f}  lead {lt}  conf {r.confidence:.0%}")
    if not summary["lead_time"]:
        print("\n(live fire: ablation & lead-time delta require a pre-registered retrospective with a"
              "\n perimeter time-series, see docs/EVALUATION.md. This view is the live forward forecast.)")
        print(f"\nCOP written: {summary['cop_path']}")
        print(f"figures: {', '.join(summary['figures'].values())}")
        print("=" * 74)
        return
    print("\n'Moved-the-needle', warning lead-time before the fire arrives (ON vs OFF baseline):")
    print(f"  {'zone':<15}{'truth@':>7}{'ON lead':>9}{'OFF lead':>9}   verdict")
    for L in summary["lead_time"]:
        ta = f"{L['truth_arrival_min']:.0f}m" if L["truth_arrival_min"] is not None else "n/a"
        onl = f"+{L['on_lead_min']:.0f}m" if L["on_lead_min"] is not None else "-"
        offl = f"+{L['off_lead_min']:.0f}m" if L["off_lead_min"] is not None else "-"
        if L["on_lead_min"] is not None and L["off_lead_min"] is None:
            verdict = f"ON warns {L['on_lead_min']:.0f} min early; baseline misses it"
        elif L["lead_delta_min"]:
            verdict = f"ON warns {L['lead_delta_min']:.0f} min earlier"
        elif L["truth_arrival_min"] and L["truth_arrival_min"] > 500:
            verdict = "protected (barrier), not threatened"
        else:
            verdict = "same"
        print(f"  {L['zone']:<15}{ta:>7}{onl:>9}{offl:>9}   {verdict}")
    print(f"\nCOP written: {summary['cop_path']}")
    print(f"figures: {', '.join(summary['figures'].values())}")
    print("=" * 74)


def main() -> None:
    p = argparse.ArgumentParser(description="FIREWATCH reproducible replay")
    p.add_argument("--fire", required=True, help="event id to replay (use 'demo' for the offline synthetic event)")
    p.add_argument("--members", type=int, default=60, help="ensemble size")
    args = p.parse_args()
    run_replay(args.fire, n_members=args.members)


if __name__ == "__main__":
    main()
