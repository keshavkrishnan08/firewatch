"""Read-only natural-language query over the ontology (FR-API-3, stretch).

Deliberately thin: a small intent parser maps plain-English questions to read-only ontology queries
and returns answers that **cite the object ids** they came from. No writes, no autonomous action -
just a convenience over the source of truth (CLAUDE.md: the NL layer is a flourish, not the substance).
"""
from __future__ import annotations

import re
from datetime import datetime

from firewatch.ontology.store import Store


def answer_query(store: Store, question: str, at: datetime | None = None) -> dict:
    q = question.lower().strip()

    def cite(objs):
        return [o.id for o in objs]

    # which zones are most at risk / evacuate
    if re.search(r"evacuat|at risk|urgent|threat", q) and "road" not in q:
        recs = [r for r in store.state_at("Recommendation", at) if r.kind.value == "evacuate"]
        recs.sort(key=lambda r: r.urgency, reverse=True)
        top = recs[:5]
        return {
            "question": question,
            "answer": "Zones ranked by evacuation urgency: "
            + ("; ".join(f"{r.target_name} (urgency {r.urgency:.2f}, "
                         f"lead {r.lead_time_min:.0f} min)" if r.lead_time_min is not None else f"{r.target_name} (urgency {r.urgency:.2f})"
                         for r in top) or "none flagged"),
            "cites": cite(top),
        }
    # egress / roads
    if "road" in q or "egress" in q or "route" in q:
        recs = [r for r in store.state_at("Recommendation", at) if r.kind.value == "close_road"]
        recs.sort(key=lambda r: r.urgency, reverse=True)
        return {"question": question,
                "answer": "Egress routes by threat: " + ("; ".join(f"{r.target_name} (conf {r.confidence:.0%})" for r in recs[:5]) or "none flagged"),
                "cites": cite(recs[:5])}
    # staging
    if "stag" in q or "resource" in q or "crew" in q:
        recs = [r for r in store.state_at("Recommendation", at) if r.kind.value == "stage"]
        recs.sort(key=lambda r: r.urgency, reverse=True)
        return {"question": question,
                "answer": "Suggested staging: " + ("; ".join(f"{r.target_name}" for r in recs[:4]) or "none"),
                "cites": cite(recs[:4])}
    # cameras
    if "camera" in q:
        cams = store.state_at("Camera", at)
        return {"question": question, "answer": f"{len(cams)} cameras: " + ", ".join(c.name for c in cams), "cites": cite(cams)}
    # observations / feeds
    if "observ" in q or "feed" in q or "hotspot" in q or "satellite" in q:
        obs = store.state_at("Observation", at)
        kinds: dict[str, int] = {}
        for o in obs:
            kinds[o.kind.value] = kinds.get(o.kind.value, 0) + 1
        return {"question": question,
                "answer": f"{len(obs)} observations assimilated, " + ", ".join(f"{k}: {v}" for k, v in kinds.items()),
                "cites": cite(obs[:10])}
    # fire status
    if "fire" in q or "status" in q:
        fires = store.state_at("Fire", at)
        return {"question": question,
                "answer": "; ".join(f"{f.name}, status {f.status.value}" for f in fires) or "no fire on record",
                "cites": cite(fires)}

    return {
        "question": question,
        "answer": "Try asking about: which zones to evacuate, egress routes, staging, cameras, observations/feeds, or fire status.",
        "cites": [],
    }
