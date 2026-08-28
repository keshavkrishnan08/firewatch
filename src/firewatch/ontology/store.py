"""Versioned, time-indexed ontology store (FR-ONT-2).

An append-only log of object *versions*, backed by DuckDB. Every write appends a row keyed by
(kind, obj_id, valid_time, seq); reads reconstruct the world "as of" any instant by taking, per
object id, the most recent version whose valid-time is ≤ the query time. That single property is
what powers the UI time-scrubber and the retrospective replay, no future data leaks into a past
state (a causal-masking guarantee we test in tests/).

DuckDB + JSON is deliberately lightweight: no server, trivial to set up, and versioned queries come
for free (docs/ARCHITECTURE.md §4). `:memory:` is supported for tests.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from firewatch.ontology.objects import OBJECT_TYPES, OntologyObject


def _naive_utc(dt: datetime) -> datetime:
    """DuckDB TIMESTAMP is tz-naive; normalize everything to naive-UTC for the index column."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class Store:
    """Append-only, versioned object store with as-of-time reads."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS object_versions (
                seq      BIGINT,
                kind     VARCHAR,
                obj_id   VARCHAR,
                valid_t  TIMESTAMP,
                tx_t     TIMESTAMP,
                data     VARCHAR
            );
            """
        )
        self.con.execute("CREATE SEQUENCE IF NOT EXISTS seq_object_versions START 1;")
        self.con.execute(
            "CREATE INDEX IF NOT EXISTS idx_ov_kind_id ON object_versions(kind, obj_id, valid_t);"
        )

    # ── writes ────────────────────────────────────────────────────────────────

    def put(self, obj: OntologyObject) -> str:
        """Append a new version of `obj`. Returns the object id."""
        seq = self.con.execute("SELECT nextval('seq_object_versions')").fetchone()[0]
        self.con.execute(
            "INSERT INTO object_versions VALUES (?, ?, ?, ?, ?, ?)",
            [
                seq,
                obj.type_name,
                obj.id,
                _naive_utc(obj.t),
                _naive_utc(datetime.now(UTC)),
                obj.model_dump_json(),
            ],
        )
        return obj.id

    def put_many(self, objs: Iterable[OntologyObject]) -> int:
        n = 0
        for o in objs:
            self.put(o)
            n += 1
        return n

    # ── reads (as-of-time) ──────────────────────────────────────────────────────

    def _rehydrate(self, kind: str, rows: list[tuple]) -> list[OntologyObject]:
        cls = OBJECT_TYPES[kind]
        return [cls.model_validate_json(r[0]) for r in rows]

    def state_at(self, kind: str, at: datetime | None = None) -> list[OntologyObject]:
        """All current objects of `kind` as of time `at` (latest version per id with valid_t ≤ at).

        `at=None` means "now" (the latest version of every object).
        """
        at_naive = _naive_utc(at) if at is not None else datetime(9999, 1, 1)
        rows = self.con.execute(
            """
            SELECT data FROM (
                SELECT data,
                       row_number() OVER (PARTITION BY obj_id ORDER BY valid_t DESC, seq DESC) AS rn
                FROM object_versions
                WHERE kind = ? AND valid_t <= ?
            ) WHERE rn = 1
            """,
            [kind, at_naive],
        ).fetchall()
        return self._rehydrate(kind, rows)

    def get(self, kind: str, obj_id: str, at: datetime | None = None) -> OntologyObject | None:
        at_naive = _naive_utc(at) if at is not None else datetime(9999, 1, 1)
        rows = self.con.execute(
            """
            SELECT data FROM object_versions
            WHERE kind = ? AND obj_id = ? AND valid_t <= ?
            ORDER BY valid_t DESC, seq DESC LIMIT 1
            """,
            [kind, obj_id, at_naive],
        ).fetchall()
        objs = self._rehydrate(kind, rows)
        return objs[0] if objs else None

    def history(self, kind: str, obj_id: str) -> list[OntologyObject]:
        rows = self.con.execute(
            "SELECT data FROM object_versions WHERE kind = ? AND obj_id = ? ORDER BY valid_t, seq",
            [kind, obj_id],
        ).fetchall()
        return self._rehydrate(kind, rows)

    # ── introspection ───────────────────────────────────────────────────────────

    def kinds(self) -> list[str]:
        rows = self.con.execute("SELECT DISTINCT kind FROM object_versions ORDER BY kind").fetchall()
        return [r[0] for r in rows]

    def count(self, kind: str | None = None) -> int:
        if kind is None:
            return self.con.execute("SELECT count(*) FROM object_versions").fetchone()[0]
        return self.con.execute(
            "SELECT count(*) FROM object_versions WHERE kind = ?", [kind]
        ).fetchone()[0]

    def time_bounds(self) -> tuple[datetime | None, datetime | None]:
        """(earliest valid_t, latest valid_t) across all objects, drives the scrubber range."""
        row = self.con.execute(
            "SELECT min(valid_t), max(valid_t) FROM object_versions"
        ).fetchone()
        lo = row[0].replace(tzinfo=UTC) if row[0] is not None else None
        hi = row[1].replace(tzinfo=UTC) if row[1] is not None else None
        return lo, hi

    def observation_times(self, kind: str = "Observation") -> list[datetime]:
        """Distinct observation timestamps (drives the assimilation loop scheduling)."""
        rows = self.con.execute(
            "SELECT DISTINCT valid_t FROM object_versions WHERE kind = ? ORDER BY valid_t", [kind]
        ).fetchall()
        return [r[0].replace(tzinfo=UTC) for r in rows]

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
