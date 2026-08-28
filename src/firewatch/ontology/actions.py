"""Ontology actions, the verbs that change state, each logged with its evidence (FR-ONT-3).

These are thin, auditable wrappers over the store. The heavier verbs (`assimilate`,
`georeference_camera_front`, `recommend_*`) live in their own modules (forecast/, perception/,
decision/) and emit ontology objects; the helpers here cover ingestion and the *human* decisions
(acknowledge / override), which are never automated (CLAUDE.md guardrail).
"""
from __future__ import annotations

from firewatch.ontology.objects import Observation, Recommendation
from firewatch.ontology.store import Store


def ingest_observation(store: Store, obs: Observation) -> str:
    """Write an Observation (provenance already attached by the connector)."""
    return store.put(obs)


def acknowledge(store: Store, rec: Recommendation, user: str) -> Recommendation:
    """Record a human acknowledging a recommendation. Never automated."""
    rec.acknowledged_by = user
    store.put(rec)
    return rec


def override(store: Store, rec: Recommendation, user: str, note: str = "") -> Recommendation:
    """Record a human overriding a recommendation, with an optional note in the rationale."""
    rec.acknowledged_by = user
    if note:
        rec.rationale = f"{rec.rationale}\n[override by {user}] {note}".strip()
    store.put(rec)
    return rec
