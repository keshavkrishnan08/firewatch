"""Learned smoke segmenter (FR-PER-1/2) — a small U-Net trained on real torch.

Detection/segmentation are commodity inputs (docs/LITERATURE_REVIEW.md §1–2); this provides a genuine
*learned* torch model on the ML path (not the classical heuristic), trained by self-supervision on a
procedurally-generated tower-cam frame set with ground-truth plume masks. It runs on MPS/CUDA/CPU and
reports a validation mask-IoU. Honesty: it is trained on synthetic frames; FIgLib/SmokeyNet-trained
weights (real imagery) are a drop-in replacement — the interface is identical.

Requires the `ml` extra (torch). Absent torch, perception uses the classical fallback.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _device():
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def default_checkpoint():
    import os

    from firewatch.config import REPO_ROOT

    env = os.environ.get("FIREWATCH_SMOKE_WEIGHTS")
    return env if env else str(REPO_ROOT / "data" / "models" / "smoke_net.pt")


def load_if_available():
    """Return a trained SmokeSegmenter if a checkpoint + torch are present, else None (graceful)."""
    from pathlib import Path

    ckpt = default_checkpoint()
    if not Path(ckpt).exists():
        return None
    try:
        return SmokeSegmenter.load(ckpt)
    except Exception:
        return None


# ── procedural training data: tower-cam frames with plume masks ──────────────────


def synth_smoke_frame(rng, W=256, H=192) -> tuple[np.ndarray, np.ndarray]:
    """A plausible frame (BGR uint8) + ground-truth smoke mask (bool). ~half have no smoke."""
    img = np.zeros((H, W, 3), dtype=np.float32)
    horizon = int(H * rng.uniform(0.35, 0.6)) + (rng.standard_normal(W) * 2).astype(int)
    yy = np.arange(H)[:, None]
    sky = yy < horizon[None, :]
    depth = np.clip(yy / H, 0, 1)  # (H, 1)
    sky_bgr = np.array([rng.uniform(160, 210), rng.uniform(120, 180), rng.uniform(80, 150)])
    gnd_bgr = np.array([rng.uniform(50, 90), rng.uniform(80, 130), rng.uniform(60, 110)])
    for c in range(3):
        img[..., c] = np.where(sky, sky_bgr[c] + 40 * depth, gnd_bgr[c] - 25 * depth)
    # some clouds (low-sat bright blobs) as distractors
    for _ in range(rng.integers(0, 3)):
        cx, cy = rng.uniform(0, W), rng.uniform(0, horizon.mean() * 0.7)
        XX, YY = np.meshgrid(np.arange(W), np.arange(H))
        blob = np.exp(-(((XX - cx) ** 2) / (2 * rng.uniform(20, 60) ** 2) + ((YY - cy) ** 2) / (2 * rng.uniform(8, 20) ** 2)))
        img += (blob[..., None] * rng.uniform(20, 50))

    mask = np.zeros((H, W), dtype=bool)
    if rng.random() < 0.6:  # 60% of frames contain a plume
        px = rng.uniform(W * 0.2, W * 0.8)
        base = int(horizon.mean() + rng.uniform(-10, 10))
        top = int(base - rng.uniform(H * 0.3, H * 0.8))
        XX, YY = np.meshgrid(np.arange(W).astype(float), np.arange(H).astype(float))
        hnorm = np.clip((base - YY) / max(base - top, 1), 0, 1)
        axis = px + rng.uniform(-0.3, 0.3) * (base - YY) + rng.uniform(4, 10) * np.sin(YY / rng.uniform(15, 30))
        width = rng.uniform(6, 16) + rng.uniform(30, 90) * hnorm
        soft = np.clip(1 - np.abs(XX - axis) / np.maximum(width, 1), 0, 1) * (YY < base) * (YY > top)
        soft *= 0.6 + 0.4 * rng.random((H, W))
        gray = rng.uniform(170, 210)
        alpha = np.clip(soft * rng.uniform(1.1, 1.6), 0, 0.95)
        for c in range(3):
            img[..., c] = img[..., c] * (1 - alpha) + gray * alpha
        mask = soft > 0.25

    img += rng.standard_normal(img.shape) * 4
    return np.clip(img, 0, 255).astype(np.uint8), mask


def _build_unet():
    import torch.nn as nn

    def cbr(ci, co):
        return nn.Sequential(nn.Conv2d(ci, co, 3, padding=1), nn.GroupNorm(8, co), nn.GELU(),
                             nn.Conv2d(co, co, 3, padding=1), nn.GroupNorm(8, co), nn.GELU())

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.d1, self.d2, self.d3 = cbr(3, 32), cbr(32, 64), cbr(64, 128)
            self.pool = nn.MaxPool2d(2)
            self.u2, self.c2 = nn.ConvTranspose2d(128, 64, 2, 2), cbr(128, 64)
            self.u1, self.c1 = nn.ConvTranspose2d(64, 32, 2, 2), cbr(64, 32)
            self.out = nn.Conv2d(32, 1, 1)

        def forward(self, x):
            import torch
            x1 = self.d1(x)
            x2 = self.d2(self.pool(x1))
            x3 = self.d3(self.pool(x2))
            y = self.c2(torch.cat([self.u2(x3), x2], 1))
            y = self.c1(torch.cat([self.u1(y), x1], 1))
            return self.out(y)

    return UNet()


@dataclass
class SmokeSegmenter:
    net: object
    device: object
    size: tuple[int, int] = (192, 256)  # (H, W) the net runs at

    def segment(self, image_bgr: np.ndarray, thresh: float = 0.5) -> np.ndarray:
        import cv2
        import torch

        H0, W0 = image_bgr.shape[:2]
        img = cv2.resize(image_bgr, (self.size[1], self.size[0])).astype(np.float32) / 255.0
        x = torch.from_numpy(img.transpose(2, 0, 1)[None]).to(self.device)
        with torch.no_grad():
            p = torch.sigmoid(self.net(x)).cpu().numpy()[0, 0]
        return cv2.resize((p > thresh).astype(np.uint8), (W0, H0)).astype(bool)

    def save(self, path):
        import torch

        torch.save(self.net.state_dict(), path)

    @classmethod
    def load(cls, path):
        import torch

        dev = _device()
        net = _build_unet().to(dev)
        net.load_state_dict(torch.load(path, map_location=dev))
        net.eval()
        return cls(net=net, device=dev)


def _dice_iou(pred, target):
    inter = (pred & target).sum()
    union = (pred | target).sum()
    return float(inter / union) if union > 0 else 1.0


def train_smoke_net(n_train=600, n_val=120, epochs=12, batch=16, seed=0, log=print) -> tuple[SmokeSegmenter, dict]:
    import time

    import torch

    rng = np.random.default_rng(seed)
    H, W = 192, 256
    log(f"generating {n_train + n_val} synthetic tower-cam frames…")
    data = [synth_smoke_frame(rng, W, H) for _ in range(n_train + n_val)]
    X = np.stack([d[0].astype(np.float32).transpose(2, 0, 1) / 255.0 for d in data])
    Y = np.stack([d[1][None].astype(np.float32) for d in data])
    Xtr, Ytr = torch.from_numpy(X[:n_train]), torch.from_numpy(Y[:n_train])
    Xva, Yva = torch.from_numpy(X[n_train:]), torch.from_numpy(Y[n_train:])

    dev = _device()
    net = _build_unet().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    bce = torch.nn.BCEWithLogitsLoss()
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n_train)
        tot = 0.0
        for i in range(0, n_train, batch):
            idx = perm[i:i + batch]
            xb, yb = Xtr[idx].to(dev), Ytr[idx].to(dev)
            opt.zero_grad()
            logits = net(xb)
            loss = bce(logits, yb) + _soft_dice_loss(torch.sigmoid(logits), yb)
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(idx)
        if (ep + 1) % 3 == 0 or ep == 0:
            iou = _val_iou(net, Xva, Yva, dev)
            log(f"  epoch {ep+1:>2}/{epochs}  loss {tot/n_train:.4f}  val_mask_IoU {iou:.3f}")
    train_s = time.time() - t0
    iou = _val_iou(net, Xva, Yva, dev)
    net.eval()
    return SmokeSegmenter(net=net, device=dev), {"val_mask_iou": iou, "train_seconds": train_s,
                                                  "device": str(dev), "n_train": n_train, "epochs": epochs}


def _soft_dice_loss(p, y, eps=1e-6):
    num = 2 * (p * y).sum() + eps
    den = p.sum() + y.sum() + eps
    return 1 - num / den


def _val_iou(net, Xva, Yva, dev):
    import torch

    net.eval()
    with torch.no_grad():
        p = torch.sigmoid(net(Xva.to(dev))).cpu().numpy() > 0.5
    y = Yva.numpy() > 0.5
    return float(np.mean([_dice_iou(p[i, 0], y[i, 0]) for i in range(len(p))]))
