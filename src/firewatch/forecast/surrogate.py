"""Learned spread surrogate (FR-FC-5) — a small CNN that emulates the physical MTT prior.

The surrogate is a fully-convolutional network trained by self-distillation: it learns to reproduce
the Minimum-Travel-Time arrival field of the Rothermel physical model from the model's own input
channels (ROS magnitude, head direction, eccentricity, and the ignition distance transform). At
inference it predicts the arrival field in a single forward pass — a fast approximate prior — while
the assimilation + calibration loop (the actual contribution) stays unchanged. `make train` trains it
on **real California landscapes** (real DEM + ESA WorldCover fuels sampled from `firewatch.landscapes`);
only the wind/moisture forcings are randomized, exactly as an ensemble perturbs them. Honesty
(CLAUDE.md): the emulation target is our physical model; WildfireSpreadTS/Next-Day pretraining is future work.

Requires the `ml` extra (torch). Everything degrades gracefully if torch is absent.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from firewatch.forecast.grid import synthetic_grid
from firewatch.forecast.spread import SpreadParams, precompute_ros, solve_arrival_times

T_SCALE = 240.0  # minutes; arrival normalized to [0,1] for training


def _device():
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def input_channels(grid, ignition_lonlat, params: SpreadParams | None = None) -> np.ndarray:
    """Build the (C, H, W) input stack the surrogate consumes."""
    from scipy.ndimage import distance_transform_edt

    ros = precompute_ros(grid, params or SpreadParams())
    ign = grid.ignition_mask(ignition_lonlat, radius_m=grid.cell_m)
    dt = distance_transform_edt(~ign) * grid.cell_m / (grid.cell_m * grid.nx)  # normalized 0..~1
    r = ros["r_head"] / 3.0  # ~0..1 (cap 3 m/s)
    return np.stack([r, ros["hx"], ros["hy"], ros["ecc"], dt.astype(np.float32)]).astype(np.float32)


def _build_model():
    import torch.nn as nn

    def block(ci, co, d):
        return nn.Sequential(nn.Conv2d(ci, co, 3, padding=d, dilation=d), nn.GroupNorm(8, co), nn.GELU())

    return nn.Sequential(
        block(5, 32, 1), block(32, 48, 2), block(48, 64, 4), block(64, 64, 8),
        block(64, 48, 16), block(48, 32, 1),
        nn.Conv2d(32, 1, 1), nn.Softplus(),  # arrival >= 0
    )


@dataclass
class SurrogateModel:
    net: object
    device: object

    def predict_arrival(self, grid, ignition_lonlat, params: SpreadParams | None = None) -> np.ndarray:
        import torch

        x = input_channels(grid, ignition_lonlat, params)
        with torch.no_grad():
            t = torch.from_numpy(x[None]).to(self.device)
            y = self.net(t).cpu().numpy()[0, 0]
        arrival = y * T_SCALE
        arrival[arrival >= T_SCALE * 0.99] = np.inf  # treat saturated as unreached
        return arrival

    def save(self, path):
        import torch

        torch.save(self.net.state_dict(), path)

    @classmethod
    def load(cls, path):
        import torch

        dev = _device()
        net = _build_model().to(dev)
        net.load_state_dict(torch.load(path, map_location=dev))
        net.eval()
        return cls(net=net, device=dev)


def _real_grid(item, rng, n=96):
    """Build a FireGrid from a random window of a real (DEM + WorldCover) landscape."""
    from firewatch.forecast.grid import FireGrid

    E, F = item["elev"], item["fuel"]
    h, w = E.shape
    i0 = int(rng.integers(0, max(1, h - n)))
    j0 = int(rng.integers(0, max(1, w - n)))
    elev = E[i0:i0 + n, j0:j0 + n].astype(float)
    fuel = F[i0:i0 + n, j0:j0 + n].astype(int)
    ws, wd = float(rng.uniform(2, 14)), float(rng.uniform(0, 360))
    u, v = ws * np.sin(np.radians(wd)), ws * np.cos(np.radians(wd))
    moist = float(rng.uniform(0.04, 0.16))
    return FireGrid(item["lat"], item["lon"], item["cell_m"], elev, fuel,
                    np.full((n, n), u), np.full((n, n), v), np.full((n, n), moist))


def _sample(rng, n=96, bank=None):
    """One (input, target-arrival) example from the physical solver on a real or synthetic grid."""
    if bank:
        grid = _real_grid(bank[int(rng.integers(len(bank)))], rng, n)
    else:
        grid = synthetic_grid(34 + rng.random() * 8, -124 + rng.random() * 8, cell_m=200.0, n=n,
                              wind_speed_ms=float(rng.uniform(2, 14)), wind_dir_to_deg=float(rng.uniform(0, 360)),
                              base_fuel=int(rng.choice([1, 2, 5, 10])), moisture=float(rng.uniform(0.04, 0.16)),
                              seed=int(rng.integers(1, 1_000_000)))
    ign = grid.cell_to_lonlat(n // 2 + int(rng.integers(-8, 8)), n // 2 + int(rng.integers(-8, 8)))
    arr = solve_arrival_times(grid, grid.ignition_mask(ign, radius_m=grid.cell_m), SpreadParams())
    x = input_channels(grid, ign)
    y = np.clip(np.nan_to_num(arr, posinf=T_SCALE * 1.5) / T_SCALE, 0, 1).astype(np.float32)
    return x, y[None]


def train_surrogate(n_train=400, n_val=60, epochs=30, batch=8, seed=0, bank=None, log=print) -> tuple[SurrogateModel, dict]:
    """Self-distill the physical MTT solver into the CNN. If `bank` (real landscapes) is given, train
    on real terrain + fuels; otherwise fall back to synthetic grids. Returns (model, metrics)."""
    import time

    import torch

    rng = np.random.default_rng(seed)
    src = f"{len(bank)} real landscapes" if bank else "synthetic grids"
    log(f"generating {n_train + n_val} physical-model samples on {src}…")
    data = [_sample(rng, bank=bank) for _ in range(n_train + n_val)]
    X = torch.from_numpy(np.stack([d[0] for d in data]))
    Y = torch.from_numpy(np.stack([d[1] for d in data]))
    Xtr, Ytr, Xva, Yva = X[:n_train], Y[:n_train], X[n_train:], Y[n_train:]

    dev = _device()
    net = _build_model().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1.5e-3)
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n_train)
        tot = 0.0
        for i in range(0, n_train, batch):
            idx = perm[i:i + batch]
            xb, yb = Xtr[idx].to(dev), Ytr[idx].to(dev)
            opt.zero_grad()
            # weight reached cells (arrival < horizon) far more than the trivial unreached tail
            w = 1.0 + 8.0 * (yb < 0.99).float()
            loss = (w * (net(xb) - yb) ** 2).mean()
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(idx)
        if (ep + 1) % 5 == 0 or ep == 0:
            rmae = _reached_mae(net, Xva, Yva, dev)
            log(f"  epoch {ep+1:>2}/{epochs}  train_loss {tot/n_train:.4f}  reached_MAE {rmae:.1f} min")
    train_s = time.time() - t0

    # meaningful metrics: MAE on cells the fire actually reached, + +60-min perimeter IoU
    net.eval()
    with torch.no_grad():
        vpred = net(Xva.to(dev)).cpu().numpy()
    vtrue = Yva.numpy()
    reached = vtrue < 0.99
    reached_mae = float(np.abs(vpred[reached] - vtrue[reached]).mean() * T_SCALE) if reached.any() else float("nan")
    h60 = 60.0 / T_SCALE
    iou60 = _mask_iou(vpred < h60, vtrue < h60)
    model = SurrogateModel(net=net, device=dev)

    # honest speed: the real use is one BATCHED forward for the whole ensemble vs N MTT solves
    N, n = 48, 160
    g = synthetic_grid(38.5, -122.6, cell_m=200.0, n=n, wind_speed_ms=9, wind_dir_to_deg=60)
    igs = [g.cell_to_lonlat(n // 2 + int(d), n // 2) for d in np.linspace(-6, 6, N)]
    ps = [SpreadParams(wind_mult=float(w)) for w in np.linspace(0.7, 1.4, N)]
    t = time.time()
    for ig, p in zip(igs, ps, strict=False):
        solve_arrival_times(g, g.ignition_mask(ig, 200), p)
    t_mtt = time.time() - t
    t = time.time()
    Xb = torch.from_numpy(np.stack([input_channels(g, ig, p) for ig, p in zip(igs, ps, strict=False)]))
    with torch.no_grad():
        net(Xb.to(dev)).cpu().numpy()
    t_sur = time.time() - t
    metrics = {"val_mae_min": reached_mae, "reached_mae_min": reached_mae, "perimeter_iou_60": iou60,
               "train_seconds": train_s, "device": str(dev), "ensemble_n": N, "grid_n": n,
               "surrogate_ms": t_sur * 1000, "mtt_ms": t_mtt * 1000, "speedup": t_mtt / max(t_sur, 1e-6),
               "n_train": n_train, "epochs": epochs, "training_data": src}
    return model, metrics


def _reached_mae(net, X, Y, dev) -> float:
    import torch

    net.eval()
    with torch.no_grad():
        p = net(X.to(dev)).cpu().numpy()
    y = Y.numpy()
    reached = y < 0.99
    return float(np.abs(p[reached] - y[reached]).mean() * T_SCALE) if reached.any() else float("nan")


def _mask_iou(a, b) -> float:
    inter = (a & b).sum()
    union = (a | b).sum()
    return float(inter / union) if union > 0 else 1.0
