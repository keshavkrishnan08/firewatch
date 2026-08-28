"""Learned smoke segmenter (FR-PER-1/2), a small U-Net trained on real torch.

Detection/segmentation are commodity inputs (docs/LITERATURE_REVIEW.md §1-2); this provides a genuine
*learned* torch model on the ML path (not the classical heuristic). `make train` trains it on **real
wildfire-camera imagery**, the Pyronear `pyro-sdis` dataset (HuggingFace, keyless), with box-
supervised masks refined by the smoke-likelihood field (`train_smoke_net_real`). When that dataset is
unreachable it falls back to procedurally-generated frames (`train_smoke_net`, clearly labeled). Runs
on MPS/CUDA/CPU and reports a validation mask-IoU; FIgLib/SmokeyNet weights are a drop-in.

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


# procedural training data: tower-cam frames with plume masks


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


# real wildfire imagery: Pyronear pyro-sdis (HuggingFace, keyless)


def _mask_from_boxes(img_bgr, boxes, W, H):
    """Box-supervised mask refined by the smoke-likelihood field inside each box (real weak labels)."""
    from firewatch.perception.detect import smoke_likelihood

    mask = np.zeros((H, W), dtype=bool)
    if not boxes:
        return mask
    lk = smoke_likelihood(img_bgr)
    for cx, cy, bw, bh in boxes:
        x1, x2 = int((cx - bw / 2) * W), int((cx + bw / 2) * W)
        y1, y2 = int((cy - bh / 2) * H), int((cy + bh / 2) * H)
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(W, x2), min(H, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        sub = lk[y1:y2, x1:x2]
        sm = sub >= max(0.35, float(np.percentile(sub, 55)))
        if sm.sum() < 0.15 * sm.size:  # refinement too sparse -> fall back to the box
            sm[:] = True
        mask[y1:y2, x1:x2] |= sm
    return mask


def load_pyro_sdis(n=800, n_neg=200, W=256, H=192, seed=0, log=print):
    """Load real wildfire-camera images + smoke boxes from Pyronear pyro-sdis; build (img, mask) pairs."""
    import io

    import cv2
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    from PIL import Image

    path = hf_hub_download("pyronear/pyro-sdis", "data/train-00000-of-00006.parquet", repo_type="dataset")
    pf = pq.ParquetFile(path)
    pairs, negs = [], []
    for batch in pf.iter_batches(batch_size=64):
        imgs = batch.column("image")
        anns = batch.column("annotations")
        for i in range(len(imgs)):
            if len(pairs) >= n and len(negs) >= n_neg:
                break
            ann = anns[i].as_py() or ""
            boxes = []
            for line in ann.strip().splitlines():
                p = line.split()
                if len(p) == 5:
                    boxes.append(tuple(float(v) for v in p[1:5]))
            rec = imgs[i].as_py()
            b = rec["bytes"] if isinstance(rec, dict) else rec
            try:
                im = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))[..., ::-1]  # -> BGR
            except Exception:
                continue
            img = cv2.resize(im, (W, H))
            if boxes and len(pairs) < n:
                pairs.append((img, _mask_from_boxes(img, boxes, W, H)))
            elif not boxes and len(negs) < n_neg:
                negs.append((img, np.zeros((H, W), dtype=bool)))
        if len(pairs) >= n and len(negs) >= n_neg:
            break
    log(f"pyro-sdis: {len(pairs)} smoke + {len(negs)} negative real images")
    data = pairs + negs
    np.random.default_rng(seed).shuffle(data)
    return data


def train_smoke_net_real(n=900, n_val=180, epochs=14, batch=16, seed=0, log=print) -> tuple[SmokeSegmenter, dict]:
    """Train the smoke U-Net on REAL Pyronear wildfire imagery (box-supervised, likelihood-refined)."""
    import time

    import cv2
    import torch

    data = load_pyro_sdis(n=n, n_neg=n // 4, seed=seed, log=log)
    if len(data) < 60:
        raise RuntimeError("insufficient real images")
    H, W = 192, 256
    X = np.stack([cv2.resize(d[0], (W, H)).astype(np.float32).transpose(2, 0, 1) / 255.0 for d in data])
    Y = np.stack([d[1][None].astype(np.float32) for d in data])
    nt = len(data) - n_val
    Xtr, Ytr = torch.from_numpy(X[:nt]), torch.from_numpy(Y[:nt])
    Xva, Yva = torch.from_numpy(X[nt:]), torch.from_numpy(Y[nt:])
    dev = _device()
    net = _build_unet().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    bce = torch.nn.BCEWithLogitsLoss()
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(nt)
        for i in range(0, nt, batch):
            idx = perm[i:i + batch]
            xb, yb = Xtr[idx].to(dev), Ytr[idx].to(dev)
            opt.zero_grad()
            logits = net(xb)
            loss = bce(logits, yb) + _soft_dice_loss(torch.sigmoid(logits), yb)
            loss.backward()
            opt.step()
        if (ep + 1) % 3 == 0 or ep == 0:
            log(f"  epoch {ep+1:>2}/{epochs}  val_mask_IoU {_val_iou(net, Xva, Yva, dev):.3f}")
    iou = _val_iou(net, Xva, Yva, dev)
    net.eval()
    return SmokeSegmenter(net=net, device=dev), {"val_mask_iou": iou, "train_seconds": time.time() - t0,
                                                  "device": str(dev), "n_train": nt, "epochs": epochs,
                                                  "training_data": "real Pyronear pyro-sdis imagery"}


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
