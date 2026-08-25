"""Per-frame smoke-state features (FR-PER-3): area, centroid, bearing, growth, plume tilt.

These are the cheap, physically-meaningful summaries that (a) drive the georeferenced front and
(b) give a wind proxy (plume tilt) and a growth signal for the COP readout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from firewatch.ontology.objects import Camera
from firewatch.perception.triangulate import bearing_to_plume


@dataclass
class SmokeState:
    area_px: int
    centroid_px: tuple[float, float]
    bearing_deg: float | None
    growth_rate_px_per_s: float
    plume_tilt_deg: float
    confidence: float

    def as_dict(self) -> dict:
        return {
            "area_px": self.area_px,
            "centroid_px": list(self.centroid_px),
            "bearing_deg": self.bearing_deg,
            "growth_rate_px_per_s": self.growth_rate_px_per_s,
            "plume_tilt_deg": self.plume_tilt_deg,
            "confidence": self.confidence,
        }


def plume_tilt(mask: np.ndarray) -> float:
    """Orientation of the plume's principal axis (deg from vertical; + = leaning right). A wind proxy."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 5:
        return 0.0
    xs = xs - xs.mean()
    ys = ys - ys.mean()
    cov = np.cov(np.vstack([xs, ys]))
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, int(np.argmax(evals))]
    # image y is downward; angle of the major axis from the vertical (up) direction
    ang = math.degrees(math.atan2(major[0], -major[1]))
    return float((ang + 180) % 180 - 90)


def smoke_state(
    mask: np.ndarray,
    camera: Camera | None = None,
    prev: SmokeState | None = None,
    dt_s: float = 60.0,
    confidence: float = 1.0,
) -> SmokeState:
    area = int(mask.sum())
    if area == 0:
        return SmokeState(0, (0.0, 0.0), None, 0.0, 0.0, 0.0)
    ys, xs = np.nonzero(mask)
    centroid = (float(xs.mean()), float(ys.mean()))
    bearing = bearing_to_plume(camera, mask) if camera is not None else None
    growth = (area - prev.area_px) / dt_s if prev is not None and dt_s > 0 else 0.0
    return SmokeState(
        area_px=area,
        centroid_px=centroid,
        bearing_deg=bearing,
        growth_rate_px_per_s=float(growth),
        plume_tilt_deg=plume_tilt(mask),
        confidence=float(confidence),
    )
