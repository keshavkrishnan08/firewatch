"""Runtime configuration & per-event paths.

Everything is keyed by `event_id` so a run is reproducible and cached offline (NFR-2). The data
root is gitignored; only pinned snapshots + generated figures under outputs/ are meant to persist.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency): populate os.environ from a repo-root .env if present."""
    env = REPO_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def data_dir() -> Path:
    root = os.environ.get("FIREWATCH_DATA_DIR")
    return Path(root) if root else REPO_ROOT / "data"


def outputs_dir() -> Path:
    return REPO_ROOT / "outputs"


@dataclass
class EventPaths:
    """Filesystem layout for one fire event."""

    event_id: str

    @property
    def root(self) -> Path:
        return data_dir() / "events" / self.event_id

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def ontology_db(self) -> Path:
        return self.root / "ontology.duckdb"

    @property
    def outputs(self) -> Path:
        return outputs_dir() / self.event_id

    def ensure(self) -> EventPaths:
        self.cache.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        return self


def firms_map_key() -> str | None:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    return key or None
