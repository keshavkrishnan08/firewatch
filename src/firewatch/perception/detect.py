"""Smoke / flame detection on camera frames (FR-PER-1).

Primary backend is an off-the-shelf detector (YOLO / RT-DETR via `ultralytics`) — detection is a
commodity input, not a contribution (docs/LITERATURE_REVIEW.md §1). When model weights / a GPU are
unavailable, a transparent **classical-CV fallback** keeps the whole pipeline runnable: smoke is
low-saturation, mid-value, and low-texture (hazy); flame is high-value warm-hue. The active backend
is always reported so results are never mistaken for the ML detector.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # optional heavy dep
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover
    _HAS_CV2 = False


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    score: float
    label: str  # "smoke" | "flame"
    backend: str


def smoke_likelihood(image_bgr: np.ndarray) -> np.ndarray:
    """Per-pixel smoke likelihood in [0, 1] from color + texture cues (classical fallback)."""
    img = image_bgr.astype(np.float32)
    if _HAS_CV2:
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
        s = hsv[..., 1] / 255.0
        v = hsv[..., 2] / 255.0
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
        texture = cv2.blur(np.abs(lap), (9, 9))
    else:  # pure-numpy approximation
        mx = img.max(axis=2)
        mn = img.min(axis=2)
        s = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0.0)
        v = mx / 255.0
        gray = img.mean(axis=2)
        gx = np.abs(np.gradient(gray, axis=1))
        gy = np.abs(np.gradient(gray, axis=0))
        texture = gx + gy
    low_sat = np.clip(1.0 - s / 0.35, 0.0, 1.0)
    mid_val = np.clip(1.0 - np.abs(v - 0.72) / 0.4, 0.0, 1.0)
    tnorm = texture / (np.percentile(texture, 95) + 1e-6)
    low_tex = np.clip(1.0 - tnorm, 0.0, 1.0)
    lk = low_sat * mid_val * low_tex
    m, s2 = lk.min(), lk.max()
    return (lk - m) / (s2 - m + 1e-6)


def flame_likelihood(image_bgr: np.ndarray) -> np.ndarray:
    """Per-pixel flame likelihood in [0, 1] (warm hue, very bright)."""
    b, g, r = image_bgr[..., 0].astype(np.float32), image_bgr[..., 1].astype(np.float32), image_bgr[..., 2].astype(np.float32)
    warm = np.clip((r - b) / 255.0, 0.0, 1.0) * np.clip((r - g * 0.4) / 255.0, 0.0, 1.0)
    bright = np.clip((r / 255.0 - 0.6) / 0.4, 0.0, 1.0)
    lk = warm * bright
    return lk / (lk.max() + 1e-6)


class SmokeDetector:
    """YOLO/RT-DETR if available, else the classical fallback."""

    def __init__(self, weights: str | None = None):
        self.backend = "classical"
        self.model = None
        if weights:
            try:
                from ultralytics import YOLO

                self.model = YOLO(weights)
                self.backend = "yolo"
            except Exception:
                self.model = None  # fall back silently; backend stays "classical"

    def detect(self, image_bgr: np.ndarray, thresh: float = 0.45) -> list[Detection]:
        if self.model is not None:
            return self._detect_yolo(image_bgr, thresh)
        return self._detect_classical(image_bgr, thresh)

    def _detect_yolo(self, image_bgr: np.ndarray, thresh: float) -> list[Detection]:  # pragma: no cover
        out: list[Detection] = []
        res = self.model.predict(image_bgr, verbose=False, conf=thresh)
        for r in res:
            for box in r.boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                label = r.names.get(int(box.cls[0]), "smoke")
                out.append(Detection((x1, y1, x2, y2), float(box.conf[0]), str(label), "yolo"))
        return out

    def _detect_classical(self, image_bgr: np.ndarray, thresh: float) -> list[Detection]:
        out: list[Detection] = []
        for lk_fn, label in ((smoke_likelihood, "smoke"), (flame_likelihood, "flame")):
            lk = lk_fn(image_bgr)
            mask = (lk > thresh).astype(np.uint8)
            if _HAS_CV2:
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
                n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
                comps = range(1, n)
            else:
                comps, lbl, stats = _cc_numpy(mask)
            h, w = mask.shape
            min_area = 0.001 * h * w
            for c in comps:
                x, y, bw, bh, area = stats[c][0], stats[c][1], stats[c][2], stats[c][3], stats[c][4]
                if area < min_area:
                    continue
                score = float(lk[lbl == c].mean())
                out.append(Detection((int(x), int(y), int(x + bw), int(y + bh)), score, label, "classical"))
        out.sort(key=lambda d: d.score, reverse=True)
        return out


def _cc_numpy(mask: np.ndarray):
    """Minimal connected-components fallback when OpenCV is absent (label + stats)."""
    from scipy.ndimage import find_objects
    from scipy.ndimage import label as ndlabel

    lbl, n = ndlabel(mask)
    stats = {0: (0, 0, 0, 0, 0)}
    for c, sl in enumerate(find_objects(lbl), start=1):
        if sl is None:
            continue
        ys, xs = sl
        area = int((lbl[sl] == c).sum())
        stats[c] = (xs.start, ys.start, xs.stop - xs.start, ys.stop - ys.start, area)
    return range(1, n + 1), lbl, stats
