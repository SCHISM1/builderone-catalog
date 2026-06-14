"""SQLite store — source_observations, parts, review_queue, audit_records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS source_observations (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    raw_name TEXT NOT NULL,
    engine_field_values TEXT NOT NULL,
    attributes TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parts (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    data TEXT NOT NULL,
    has_catastrophic_conflict INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    part_id TEXT,
    observation_ids TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_queue (
    id TEXT PRIMARY KEY,
    queue_type TEXT NOT NULL,
    category TEXT NOT NULL,
    observation_ids TEXT NOT NULL,
    conflict_data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_value TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
"""


@dataclass
class SourceObservationRow:
    id: str
    source_name: str
    source_content_hash: str
    category: str
    raw_name: str
    engine_field_values: dict[str, Any]
    attributes: dict[str, Any]
    method: str
    confidence: float
    timestamp: str


@dataclass
class ReviewQueueEntry:
    id: str
    queue_type: str  # "dedup" | "catastrophic_conflict"
    category: str
    observation_ids: list[str]
    conflict_data: dict[str, Any]
    status: str = "pending"
    resolved_value: Any = None
    created_at: str = field(default_factory=_now)
    resolved_at: str | None = None


@dataclass
class AuditRecord:
    id: str
    event_type: str  # "merge" | "resolve" | "flag"
    observation_ids: list[str]
    details: dict[str, Any]
    part_id: str | None = None
    created_at: str = field(default_factory=_now)


class Database:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── source_observations ───────────────────────────────────────────────────

    def save_observation(self, obs: SourceObservationRow) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO source_observations
              (id, source_name, source_content_hash, category, raw_name,
               engine_field_values, attributes, method, confidence, timestamp)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                obs.id,
                obs.source_name,
                obs.source_content_hash,
                obs.category,
                obs.raw_name,
                json.dumps(obs.engine_field_values),
                json.dumps(obs.attributes),
                obs.method,
                obs.confidence,
                obs.timestamp,
            ),
        )
        self._conn.commit()

    def get_observations_by_category(self, category: str) -> list[SourceObservationRow]:
        rows = self._conn.execute(
            "SELECT * FROM source_observations WHERE category = ?", (category,)
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_all_observations(self) -> list[SourceObservationRow]:
        rows = self._conn.execute("SELECT * FROM source_observations").fetchall()
        return [self._row_to_obs(r) for r in rows]

    def observation_exists(self, content_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM source_observations WHERE source_content_hash = ?", (content_hash,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _row_to_obs(r: sqlite3.Row) -> SourceObservationRow:
        return SourceObservationRow(
            id=r["id"],
            source_name=r["source_name"],
            source_content_hash=r["source_content_hash"],
            category=r["category"],
            raw_name=r["raw_name"],
            engine_field_values=json.loads(r["engine_field_values"]),
            attributes=json.loads(r["attributes"]),
            method=r["method"],
            confidence=r["confidence"],
            timestamp=r["timestamp"],
        )

    # ── parts ─────────────────────────────────────────────────────────────────

    def save_part(self, part_id: str, category: str, data: dict[str, Any], has_conflict: bool = False) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO parts (id, category, data, has_catastrophic_conflict, updated_at)
            VALUES (?,?,?,?,?)
            """,
            (part_id, category, json.dumps(data), int(has_conflict), _now()),
        )
        self._conn.commit()

    def get_part(self, part_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT data FROM parts WHERE id = ?", (part_id,)).fetchone()
        if row is None:
            return None
        return json.loads(row["data"])  # type: ignore[no-any-return]

    def get_all_parts(self, include_conflicted: bool = False) -> list[tuple[str, dict[str, Any], bool]]:
        """Returns list of (part_id, data, has_conflict)."""
        if include_conflicted:
            rows = self._conn.execute("SELECT id, data, has_catastrophic_conflict FROM parts").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, data, has_catastrophic_conflict FROM parts WHERE has_catastrophic_conflict = 0"
            ).fetchall()
        return [(r["id"], json.loads(r["data"]), bool(r["has_catastrophic_conflict"])) for r in rows]

    def mark_part_conflict_resolved(self, part_id: str, new_data: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE parts SET data = ?, has_catastrophic_conflict = 0, updated_at = ? WHERE id = ?",
            (json.dumps(new_data), _now(), part_id),
        )
        self._conn.commit()

    # ── review_queue ──────────────────────────────────────────────────────────

    def enqueue_review(self, entry: ReviewQueueEntry) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO review_queue
              (id, queue_type, category, observation_ids, conflict_data,
               status, resolved_value, created_at, resolved_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                entry.id,
                entry.queue_type,
                entry.category,
                json.dumps(entry.observation_ids),
                json.dumps(entry.conflict_data),
                entry.status,
                json.dumps(entry.resolved_value) if entry.resolved_value is not None else None,
                entry.created_at,
                entry.resolved_at,
            ),
        )
        self._conn.commit()

    def get_review_entry(self, entry_id: str) -> ReviewQueueEntry | None:
        row = self._conn.execute(
            "SELECT * FROM review_queue WHERE id = ?", (entry_id,)
        ).fetchone()
        return self._row_to_review(row) if row else None

    def get_pending_reviews(self, queue_type: str | None = None) -> list[ReviewQueueEntry]:
        if queue_type:
            rows = self._conn.execute(
                "SELECT * FROM review_queue WHERE status = 'pending' AND queue_type = ?",
                (queue_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM review_queue WHERE status = 'pending'"
            ).fetchall()
        return [self._row_to_review(r) for r in rows]

    def resolve_review(self, entry_id: str, resolved_value: Any) -> None:
        self._conn.execute(
            "UPDATE review_queue SET status = 'resolved', resolved_value = ?, resolved_at = ? WHERE id = ?",
            (json.dumps(resolved_value), _now(), entry_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_review(r: sqlite3.Row) -> ReviewQueueEntry:
        return ReviewQueueEntry(
            id=r["id"],
            queue_type=r["queue_type"],
            category=r["category"],
            observation_ids=json.loads(r["observation_ids"]),
            conflict_data=json.loads(r["conflict_data"]),
            status=r["status"],
            resolved_value=json.loads(r["resolved_value"]) if r["resolved_value"] else None,
            created_at=r["created_at"],
            resolved_at=r["resolved_at"],
        )

    # ── audit_records ─────────────────────────────────────────────────────────

    def save_audit_record(self, record: AuditRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_records (id, event_type, part_id, observation_ids, details, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                record.id,
                record.event_type,
                record.part_id,
                json.dumps(record.observation_ids),
                json.dumps(record.details),
                record.created_at,
            ),
        )
        self._conn.commit()

    def get_audit_records(self, part_id: str | None = None) -> list[AuditRecord]:
        if part_id:
            rows = self._conn.execute(
                "SELECT * FROM audit_records WHERE part_id = ? ORDER BY created_at", (part_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_records ORDER BY created_at"
            ).fetchall()
        return [
            AuditRecord(
                id=r["id"],
                event_type=r["event_type"],
                part_id=r["part_id"],
                observation_ids=json.loads(r["observation_ids"]),
                details=json.loads(r["details"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]


def new_id() -> str:
    return str(uuid.uuid4())
