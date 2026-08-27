"""Documented real-world evacuation timelines for the retrospective fires.

Context for the decision layer, NOT a precision claim. Published evacuation-order times are approximate
(they vary by zone and by source), so these are the earliest widely-reported mandatory order for the
community the fire ran into, in UTC, with the source. FIREWATCH's own skill is measured against GOES
ground truth (precision / recall / lead time); this table is here so the reader can see the model's
forecast-issue moment beside what actually happened on the ground.
"""
from __future__ import annotations

# key -> {community, order_utc (approx, mandatory), local, source}
EVAC_TIMELINE: dict[str, dict] = {
    "park": {
        "community": "Cohasset",
        "order_utc": "2024-07-25T02:00:00Z",
        "local": "evening of 24 Jul 2024 (PDT)",
        "source": "Cal Fire / Butte County OES incident updates",
        "approx": True,
    },
    "palisades": {
        "community": "Pacific Palisades",
        "order_utc": "2025-01-07T18:50:00Z",
        "local": "~10:50 AM PST, 07 Jan 2025",
        "source": "LAFD / CAL FIRE evacuation orders",
        "approx": True,
    },
    "eaton": {
        "community": "Altadena",
        "order_utc": "2025-01-08T03:00:00Z",
        "local": "~7:00 PM PST, 07 Jan 2025",
        "source": "LA County OEM evacuation orders",
        "approx": True,
    },
    "davis": {
        "community": "Washoe City",
        "order_utc": "2024-09-08T01:00:00Z",
        "local": "~6:00 PM PDT, 07 Sep 2024",
        "source": "Washoe County emergency management timeline",
        "approx": True,
    },
    "gray": {
        "community": "Medical Lake",
        "order_utc": "2023-08-18T20:00:00Z",
        "local": "~1:00 PM PDT, 18 Aug 2023 (Level 3, within ~1 h of ignition)",
        "source": "Spokane County / City of Medical Lake notices",
        "approx": True,
    },
}
