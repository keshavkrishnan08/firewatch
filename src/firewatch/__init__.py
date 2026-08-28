"""FIREWATCH, real-time wildfire common operating picture.

Pipeline: ingest -> perception (+georeference) -> ontology -> forecast (assimilate) -> decision -> api.
Read CLAUDE.md and docs/PRD.md before editing. The ontology is the single source of truth;
modules exchange ontology objects, never raw feed payloads.
"""
__version__ = "0.1.0"
