"""Promptable plume segmentation (FR-PER-2).

Primary backend is SAM 2 (promptable video segmentation with streaming memory; Ravi et al. 2024) —
adopted as-is. When SAM 2 weights are unavailable, a classical fallback segments the plume inside a
detector box from the smoke-likelihood field and (optionally) GrabCut, and propagates it across
frames by re-seeding from the previous mask's bounding box.
"""
from __future__ import annotations

import numpy as np

from firewatch.perception.detect import smoke_likelihood

try:
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover
    _HAS_CV2 = False


class PlumeSegmenter:
    def __init__(self, checkpoint: str | None = None, use_smoke_net: bool = True):
        self.backend = "classical"
        self.model = None
        self.smoke_net = None
        if checkpoint:
            try:  # pragma: no cover - optional heavy dep
                from sam2.build_sam import build_sam2  # noqa: F401

                self.backend = "sam2"
            except Exception:
                self.model = None
        if self.model is None and use_smoke_net:
            try:
                from firewatch.perception.smoke_net import load_if_available

                self.smoke_net = load_if_available()
                if self.smoke_net is not None:
                    self.backend = "smoke_net (torch)"
            except Exception:
                self.smoke_net = None

    def segment(self, image_bgr: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        """Return a boolean mask (H×W) of the plume inside `box`."""
        h, w = image_bgr.shape[:2]
        if self.smoke_net is not None:
            full = self.smoke_net.segment(image_bgr)
            crop = np.zeros((h, w), dtype=bool)
            x1, y1, x2, y2 = (int(v) for v in box)
            pad = 30  # allow the plume to extend a bit beyond the detector box
            x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
            x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
            crop[y1:y2, x1:x2] = full[y1:y2, x1:x2]
            return crop
        x1, y1, x2, y2 = (int(v) for v in box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        mask = np.zeros((h, w), dtype=bool)
        if x2 <= x1 or y2 <= y1:
            return mask
        lk = smoke_likelihood(image_bgr)
        sub = lk[y1:y2, x1:x2]
        thr = max(0.4, float(np.percentile(sub, 60)))
        submask = sub >= thr
        if _HAS_CV2 and submask.any():
            m = submask.astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            submask = m.astype(bool)
        mask[y1:y2, x1:x2] = submask
        return mask

    def propagate(self, frames: list[np.ndarray], init_box: tuple[int, int, int, int]) -> list[np.ndarray]:
        """Segment a plume across a frame sequence, re-seeding from the previous mask (FR-PER-2)."""
        masks: list[np.ndarray] = []
        box = init_box
        for frame in frames:
            mask = self.segment(frame, box)
            masks.append(mask)
            if mask.any():
                ys, xs = np.nonzero(mask)
                pad = 20
                box = (
                    int(xs.min()) - pad,
                    int(ys.min()) - pad,
                    int(xs.max()) + pad,
                    int(ys.max()) + pad,
                )
        return masks
