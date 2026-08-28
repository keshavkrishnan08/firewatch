"""FIREWATCH ingestion, one connector per public feed (docs/DATA_SOURCES.md).

Contract (FR-ING-1): `fetch(bbox, t0, t1) -> list[Observation | Layer]`, each with provenance
(FR-ING-3), cached per event (FR-ING-4), failing soft (FR-ING-5). Connectors: firms, goes, hrrr
(wind), dem (terrain), landfire (fuels), perimeters (NIFC), assets (OSM), cameras. `replay.build_event`
assembles a live EventBundle from all of them.
"""
