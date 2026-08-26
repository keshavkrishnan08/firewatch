"""Learned spread surrogate (FR-FC-5) — a small CNN that emulates the physical MTT prior.

The surrogate is a fully-convolutional network trained by self-distillation: it learns to reproduce
the Minimum-Travel-Time arrival field of the Rothermel physical model from the model's own input
channels (ROS magnitude, head direction, eccentricity, and the ignition distance transform). At
inference it predicts the arrival field in a single forward pass — a fast approximate prior — while
the assimilation + calibration loop (the actual contribution) stays unchanged. Honesty (CLAUDE.md):
this emulates *our* physical prior; pretraining on WildfireSpreadTS/Next-Day is future work.

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


def _sample(rng, n=96):
    """One random (input, target-arrival) training example from the physical solver."""
    lat = 34 + rng.random() * 8
    lon = -124 + rng.random() * 8
    grid = synthetic_grid(lat, lon, cell_m=200.0, n=n,
                          wind_speed_ms=float(rng.uniform(2, 14)),
                          wind_dir_to_deg=float(rng.uniform(0, 360)),
                          base_fuel=int(rng.choice([1, 2, 5, 10])),
                          moisture=float(rng.uniform(0.04, 0.16)),
                          seed=int(rng.integers(1, 1_000_000)))
    ign = grid.cell_to_lonlat(n // 2 + int(rng.integers(-8, 8)), n // 2 + int(rng.integers(-8, 8)))
    arr = solve_arrival_times(grid, grid.ignition_mask(ign, radius_m=grid.cell_m), SpreadParams())
    x = input_channels(grid, ign)
    y = np.clip(np.nan_to_num(arr, posinf=T_SCALE * 1.5) / T_SCALE, 0, 1).astype(np.float32)
    return x, y[None]


def train_surrogate(n_train=400, n_val=60, epochs=30, batch=8, seed=0, log=print) -> tuple[SurrogateModel, dict]:
    """Self-distill the physical MTT solver into the CNN. Returns (model, metrics)."""
    import time

    import torch

    rng = np.random.default_rng(seed)
    log(f"generating {n_train + n_val} physical-model samples…")
    data = [_sample(rng) for _ in range(n_train + n_val)]
    X = torch.from_numpy(np.stack([d[0] for d in data]))
    Y = torch.from_numpy(np.stack([d[1] for d in data]))
    Xtr, Ytr, Xva, Yva = X[:n_train], Y[:n_train], X[n_train:], Y[n_train:]

    dev = _device()
    net = _build_model().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    lossf = torch.nn.MSELoss()
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n_train)
        tot = 0.0
        for i in range(0, n_train, batch):
            idx = perm[i:i + batch]
            xb, yb = Xtr[idx].to(dev), Ytr[idx].to(dev)
            opt.zero_grad()
            loss = lossf(net(xb), yb)
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(idx)
        if (ep + 1) % 5 == 0 or ep == 0:
            net.eval()
            with torch.no_grad():
                vpred = net(Xva.to(dev)).cpu()
            vmae_min = float((vpred - Yva).abs().mean()) * T_SCALE
            log(f"  epoch {ep+1:>2}/{epochs}  train_mse {tot/n_train:.4f}  val_MAE {vmae_min:.1f} min")
    train_s = time.time() - t0

    # final metrics + speed comparison vs the physical solver
    net.eval()
    with torch.no_grad():
        vpred = net(Xva.to(dev)).cpu().numpy()
    vtrue = Yva.numpy()
    mae_min = float(np.abs(vpred - vtrue).mean() * T_SCALE)
    # speed: surrogate forward vs MTT solve on one grid
    g = synthetic_grid(38.5, -122.6, cell_m=200.0, n=96)
    ig = g.cell_to_lonlat(48, 48)
    model = SurrogateModel(net=net, device=dev)
    t = time.time()
    for _ in range(5):
        model.predict_arrival(g, ig)
    t_sur = (time.time() - t) / 5
    t = time.time()
    for _ in range(5):
        solve_arrival_times(g, g.ignition_mask(ig, 200), SpreadParams())
    t_mtt = (time.time() - t) / 5
    metrics = {"val_mae_min": mae_min, "train_seconds": train_s, "device": str(dev),
               "surrogate_ms": t_sur * 1000, "mtt_ms": t_mtt * 1000, "speedup": t_mtt / max(t_sur, 1e-6),
               "n_train": n_train, "epochs": epochs}
    return model, metrics
