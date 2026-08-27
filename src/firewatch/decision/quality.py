"""Decision-quality: did the forecast flag the communities that actually burned?

Precision / recall of the threat flag against ground truth. This is the "does it change a decision
correctly?" metric — separate from forecast IoU, and the thing an operator actually cares about.
"""
from __future__ import annotations

from collections.abc import Sequence


def decision_metrics(flagged: Sequence[bool], reached: Sequence[bool]) -> dict:
    """Confusion of the threat flag vs whether the fire actually reached each community.

    `flagged[i]` — the forecast crossed the threat threshold near community i.
    `reached[i]` — the GOES truth later shows fire reaching community i within the window.

    Returns counts plus precision (of the flagged, how many burned) and recall (of the burned, how
    many were flagged). Precision/recall are None when their denominator is zero.
    """
    tp = sum(1 for f, r in zip(flagged, reached, strict=True) if f and r)
    fp = sum(1 for f, r in zip(flagged, reached, strict=True) if f and not r)
    fn = sum(1 for f, r in zip(flagged, reached, strict=True) if r and not f)
    precision = round(tp / (tp + fp), 2) if (tp + fp) else None
    recall = round(tp / (tp + fn), 2) if (tp + fn) else None
    return {"flagged": tp + fp, "flagged_correct": tp, "false_alarms": fp,
            "burned": tp + fn, "missed": fn, "precision": precision, "recall": recall}
