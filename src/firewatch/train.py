"""Train the learned models (`firewatch train`): the spread surrogate + the smoke segmenter.

Both are real torch models trained by self-distillation / self-supervision (no external download),
saved under data/models/, with measured metrics and figures under outputs/ml/ + docs/assets/. See
docs/EVALUATION.md; the learned models are optional accelerators/inputs — the assimilation +
calibration loop remains the contribution.
"""
from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np

from firewatch.config import REPO_ROOT

log = logging.getLogger("firewatch.train")


def _models_dir() -> Path:
    d = REPO_ROOT / "data" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _assets_dir() -> Path:
    d = REPO_ROOT / "docs" / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def train_smoke(n_train=600, epochs=12) -> dict:
    from firewatch.perception.smoke_net import synth_smoke_frame, train_smoke_net

    model, metrics = train_smoke_net(n_train=n_train, epochs=epochs, log=lambda m: log.info(m))
    ckpt = _models_dir() / "smoke_net.pt"
    model.save(ckpt)
    metrics["checkpoint"] = str(ckpt)

    # figure: validation frames with predicted mask overlay
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(123)
    fig, axes = plt.subplots(2, 3, figsize=(11, 6))
    for ax in axes.ravel():
        img, gt = synth_smoke_frame(rng, 256, 192)
        pred = model.segment(img)
        rgb = img[..., ::-1].copy()
        rgb[pred] = (0.55 * rgb[pred] + 0.45 * np.array([255, 120, 40])).astype(np.uint8)
        ax.imshow(rgb)
        inter, union = (pred & gt).sum(), (pred | gt).sum()
        ax.set_title(f"IoU {inter/union:.2f}" if union else "no smoke", fontsize=9)
        ax.axis("off")
    fig.suptitle(f"Learned smoke segmenter (U-Net, torch/{metrics['device']}) — val mask IoU {metrics['val_mask_iou']:.2f}")
    fig.tight_layout()
    p = _assets_dir() / "smoke_net.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    metrics["figure"] = str(p)
    log.info("smoke segmenter: val IoU %.3f, trained %.0fs on %s", metrics["val_mask_iou"], metrics["train_seconds"], metrics["device"])
    return metrics


def train_surrogate_model(n_train=400, epochs=30) -> dict:
    from firewatch.forecast.grid import synthetic_grid
    from firewatch.forecast.spread import SpreadParams, solve_arrival_times
    from firewatch.forecast.surrogate import train_surrogate

    model, metrics = train_surrogate(n_train=n_train, epochs=epochs, log=lambda m: log.info(m))
    ckpt = _models_dir() / "surrogate.pt"
    model.save(ckpt)
    metrics["checkpoint"] = str(ckpt)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = synthetic_grid(38.5, -122.6, cell_m=200.0, n=96, wind_speed_ms=9, wind_dir_to_deg=60)
    ig = g.cell_to_lonlat(48, 48)
    true = solve_arrival_times(g, g.ignition_mask(ig, 200), SpreadParams())
    pred = model.predict_arrival(g, ig)
    hmax = 180.0  # show/score the operationally-relevant horizon window
    fig, ax = plt.subplots(1, 3, figsize=(12, 4))
    tshow = np.where(true <= hmax, true, np.nan)
    pshow = np.where(pred <= hmax, pred, np.nan)
    ax[0].imshow(tshow, origin="lower", cmap="magma", vmax=hmax)
    ax[0].set_title("physical MTT arrival ≤180 min")
    ax[1].imshow(pshow, origin="lower", cmap="magma", vmax=hmax)
    ax[1].set_title("learned surrogate arrival ≤180 min")
    both = (true <= hmax) & np.isfinite(pred)
    ax[2].scatter(true[both], np.clip(pred[both], 0, hmax), s=3, alpha=0.3, color="#e4572e")
    ax[2].plot([0, hmax], [0, hmax], "--", color="#888")
    ax[2].set_xlim(0, hmax)
    ax[2].set_ylim(0, hmax)
    ax[2].set_xlabel("MTT arrival (min)")
    ax[2].set_ylabel("surrogate arrival (min)")
    ax[2].set_title(f"reached-cell MAE {metrics['reached_mae_min']:.0f} min · +60m IoU {metrics['perimeter_iou_60']:.2f}")
    for a in ax[:2]:
        a.axis("off")
    fig.suptitle(f"Learned spread surrogate (FCN, torch/{metrics['device']}) — {metrics['speedup']:.0f}× faster "
                 f"than MTT for a {metrics['ensemble_n']}-member ensemble on a {metrics['grid_n']}² grid")
    fig.tight_layout()
    p = _assets_dir() / "surrogate.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    metrics["figure"] = str(p)
    log.info("surrogate: val MAE %.0f min, %.0fx faster than MTT (%.1f vs %.1f ms)",
             metrics["val_mae_min"], metrics["speedup"], metrics["surrogate_ms"], metrics["mtt_ms"])
    return metrics


def train_all(smoke_frames=600, smoke_epochs=12, surrogate_samples=400, surrogate_epochs=30) -> dict:
    warnings.simplefilter("ignore")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = {"smoke_net": train_smoke(smoke_frames, smoke_epochs),
           "surrogate": train_surrogate_model(surrogate_samples, surrogate_epochs)}
    mdir = REPO_ROOT / "outputs" / "ml"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "metrics.json").write_text(json.dumps(out, indent=2, default=str))
    print("\n=== learned models trained ===")
    print(f"  smoke segmenter: val mask IoU {out['smoke_net']['val_mask_iou']:.3f} "
          f"(torch/{out['smoke_net']['device']}) -> {out['smoke_net']['checkpoint']}")
    print(f"  spread surrogate: val MAE {out['surrogate']['val_mae_min']:.0f} min, "
          f"{out['surrogate']['speedup']:.0f}x faster than MTT -> {out['surrogate']['checkpoint']}")
    return out
