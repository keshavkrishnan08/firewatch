"""FIREWATCH perception: detect -> segment -> features -> georeference (+ skyline, triangulate).

Detection/segmentation are commodity inputs (off-the-shelf YOLO/RT-DETR + SAM2, with classical
fallbacks). The novelty lives in georeference.py + skyline.py + triangulate.py — camera→map with
self-calibration and uncertainty. See docs/LITERATURE_REVIEW.md §6b.
"""
from firewatch.perception.detect import Detection, SmokeDetector, smoke_likelihood
from firewatch.perception.features import SmokeState, smoke_state
from firewatch.perception.georeference import (
    GeorefResult,
    georeference_front,
    georeference_pixel,
    georeference_to_observation,
)
from firewatch.perception.segment import PlumeSegmenter
from firewatch.perception.skyline import (
    TiltCalibration,
    apply_calibration,
    calibrate_tilt,
    detect_skyline,
    horizon_elevation_angles,
)
from firewatch.perception.triangulate import Triangulation, bearing_to_plume, triangulate_bearings

__all__ = [
    "Detection",
    "GeorefResult",
    "PlumeSegmenter",
    "SmokeDetector",
    "SmokeState",
    "TiltCalibration",
    "Triangulation",
    "apply_calibration",
    "bearing_to_plume",
    "calibrate_tilt",
    "detect_skyline",
    "georeference_front",
    "georeference_pixel",
    "georeference_to_observation",
    "horizon_elevation_angles",
    "smoke_likelihood",
    "smoke_state",
    "triangulate_bearings",
]
