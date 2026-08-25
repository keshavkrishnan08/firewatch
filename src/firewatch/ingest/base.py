"""Shared ingest plumbing: bbox type, per-event caching, HTTP with retry, graceful degradation.

Every connector follows the same contract (FR-ING-1): `fetch(bbox, t0, t1) -> list[Observation |
Layer]`, each carrying provenance (FR-ING-3), cached per event under gitignored data/ (FR-ING-4),
and failing soft — a connector that errors logs and yields nothing rather than crashing the picture
(FR-ING-5).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger("firewatch.ingest")


@dataclass(frozen=True)
class BBox:
    minlon: float
    minlat: float
    maxlon: float
    maxlat: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.minlon + self.maxlon) / 2, (self.minlat + self.maxlat) / 2)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.minlon, self.minlat, self.maxlon, self.maxlat)

    @classmethod
    def around(cls, lon: float, lat: float, half_deg: float = 0.25) -> BBox:
        return cls(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg)


def cache_dir(event_id: str) -> Path:
    from firewatch.config import EventPaths

    d = EventPaths(event_id).cache
    d.mkdir(parents=True, exist_ok=True)
    return d


def http_get(url: str, *, params: dict | None = None, timeout: int = 30, retries: int = 3,
             headers: dict | None = None) -> requests.Response | None:
    """GET with simple exponential backoff. Returns None on persistent failure (graceful)."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=headers or {"User-Agent": "FIREWATCH/0.1"})
            if r.status_code == 200:
                return r
            log.warning("GET %s -> %s", url, r.status_code)
        except requests.RequestException as e:
            log.warning("GET %s failed (%s/%s): %s", url, attempt + 1, retries, e)
        time.sleep(1.5 * (attempt + 1))
    return None


def cached_json(event_id: str, key: str, fetch_fn, ttl_s: float | None = None):
    """Cache a JSON-able payload per event so replays are reproducible & offline (FR-ING-4)."""
    path = cache_dir(event_id) / f"{key}.json"
    if path.exists():
        if ttl_s is None or (time.time() - path.stat().st_mtime) < ttl_s:
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
    data = fetch_fn()
    if data is not None:
        path.write_text(json.dumps(data))
    return data


def soft(fn):
    """Decorator: never let a connector crash the cycle (FR-ING-5)."""
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # pragma: no cover
            log.warning("connector %s degraded: %s", getattr(fn, "__name__", fn), e)
            return []
    wrapper.__name__ = getattr(fn, "__name__", "wrapped")
    return wrapper
