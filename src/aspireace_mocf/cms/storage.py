"""CMS storage backend — SQLite catalog of records + state + provenance.

The CMS is single-tenant by design (Phase 1-3); multi-tenant Postgres backend
comes in Phase 4 / M-future. SQLite is fine for ~100K-record scale on
a single 5060 machine.

Schema (created on first connect; idempotent):
- content_records: per-record canonical state + payload + provenance
- state_transitions: append-only audit log of every state change
- content_versions: immutable snapshots per record-mutation
- comments: threaded review comments
- accuracy_flags: typed quality flags raised by reviewers / students
- review_queues: needs-review queue entries with SLA + assignment
- content_batches: batch metadata for rollback support

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
SLA: open + write a record <= 50ms; full register-batch (1K records) <= 30s.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.logging import get_logger

_log = get_logger(__name__)


DEFAULT_DB_PATH = Path("cms/catalog.sqlite")


_SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS content_records (
        content_id          TEXT PRIMARY KEY,
        record_type         TEXT NOT NULL,
        lane                TEXT NOT NULL,
        state               TEXT NOT NULL,
        state_changed_at_utc TEXT NOT NULL,
        payload_json        TEXT NOT NULL,
        payload_sha256      TEXT NOT NULL,
        source_unit_id      TEXT,
        source_id           TEXT,
        subject             TEXT,
        chapter_no          INTEGER,
        created_at_utc      TEXT NOT NULL,
        updated_at_utc      TEXT NOT NULL,
        train_allowed       INTEGER NOT NULL DEFAULT 0,
        quality_status      TEXT NOT NULL DEFAULT 'draft',
        version_number      INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS state_transitions (
        transition_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        content_id          TEXT NOT NULL,
        from_state          TEXT,
        to_state            TEXT NOT NULL,
        actor_id            TEXT NOT NULL,
        actor_role          TEXT NOT NULL,
        reason              TEXT,
        timestamp_utc       TEXT NOT NULL,
        metadata_json       TEXT,
        FOREIGN KEY (content_id) REFERENCES content_records (content_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS content_versions (
        version_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content_id          TEXT NOT NULL,
        version_number      INTEGER NOT NULL,
        payload_json        TEXT NOT NULL,
        payload_sha256      TEXT NOT NULL,
        state               TEXT NOT NULL,
        changed_by          TEXT NOT NULL,
        change_reason       TEXT,
        timestamp_utc       TEXT NOT NULL,
        FOREIGN KEY (content_id) REFERENCES content_records (content_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        comment_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content_id          TEXT NOT NULL,
        parent_comment_id   INTEGER,
        author_id           TEXT NOT NULL,
        author_role         TEXT NOT NULL,
        body                TEXT NOT NULL,
        timestamp_utc       TEXT NOT NULL,
        resolved            INTEGER NOT NULL DEFAULT 0,
        resolved_at_utc     TEXT,
        resolved_by         TEXT,
        FOREIGN KEY (content_id) REFERENCES content_records (content_id),
        FOREIGN KEY (parent_comment_id) REFERENCES comments (comment_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accuracy_flags (
        flag_id             INTEGER PRIMARY KEY AUTOINCREMENT,
        content_id          TEXT NOT NULL,
        flag_type           TEXT NOT NULL,
        severity            TEXT NOT NULL,
        flagged_by          TEXT NOT NULL,
        flagged_by_role     TEXT NOT NULL,
        flag_reason         TEXT,
        flagged_at_utc      TEXT NOT NULL,
        resolved_at_utc     TEXT,
        resolved_by         TEXT,
        resolution_action   TEXT,
        FOREIGN KEY (content_id) REFERENCES content_records (content_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_queues (
        queue_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_type          TEXT NOT NULL,
        content_id          TEXT NOT NULL,
        assigned_to         TEXT,
        enqueued_at_utc     TEXT NOT NULL,
        sla_deadline_utc    TEXT,
        priority            TEXT NOT NULL DEFAULT 'normal',
        state               TEXT NOT NULL DEFAULT 'pending',
        completed_at_utc    TEXT,
        completed_by        TEXT,
        notes               TEXT,
        FOREIGN KEY (content_id) REFERENCES content_records (content_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS content_batches (
        batch_id            TEXT PRIMARY KEY,
        description         TEXT,
        run_id              TEXT,
        created_at_utc      TEXT NOT NULL,
        record_count        INTEGER NOT NULL DEFAULT 0,
        record_ids_json     TEXT NOT NULL,
        rollback_state      TEXT NOT NULL DEFAULT 'active',
        rollback_at_utc     TEXT,
        rollback_actor      TEXT,
        rollback_reason     TEXT
    )
    """,
]

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_content_records_state ON content_records (state)",
    "CREATE INDEX IF NOT EXISTS ix_content_records_lane ON content_records (lane)",
    "CREATE INDEX IF NOT EXISTS ix_content_records_subject ON content_records (subject)",
    "CREATE INDEX IF NOT EXISTS ix_state_transitions_content ON state_transitions (content_id)",
    "CREATE INDEX IF NOT EXISTS ix_state_transitions_ts ON state_transitions (timestamp_utc)",
    "CREATE INDEX IF NOT EXISTS ix_versions_content ON content_versions (content_id, version_number)",
    "CREATE INDEX IF NOT EXISTS ix_comments_content ON comments (content_id)",
    "CREATE INDEX IF NOT EXISTS ix_comments_parent ON comments (parent_comment_id)",
    "CREATE INDEX IF NOT EXISTS ix_flags_content ON accuracy_flags (content_id)",
    "CREATE INDEX IF NOT EXISTS ix_flags_unresolved ON accuracy_flags (content_id) WHERE resolved_at_utc IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_queues_state ON review_queues (state)",
    "CREATE INDEX IF NOT EXISTS ix_queues_type_state ON review_queues (queue_type, state)",
    "CREATE INDEX IF NOT EXISTS ix_queues_assigned ON review_queues (assigned_to, state)",
    "CREATE INDEX IF NOT EXISTS ix_batches_run ON content_batches (run_id)",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _db_path(db_path: Path | str | None = None) -> Path:
    """Resolve the CMS DB path. Honors CMS_DB_PATH env var, falls back to default."""
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get("CMS_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def init_db(db_path: Path | str | None = None) -> Path:
    """Create the CMS database + apply schema if missing. Idempotent.

    Returns the resolved DB path.
    """
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        for ddl in _SCHEMA_DDL:
            conn.execute(ddl)
        for ddl in _INDEX_DDL:
            conn.execute(ddl)
        conn.commit()
    _log.info("cms_db_initialised", path=str(path))
    return path


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with sensible defaults. Always closes."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Public context manager for one-off queries. Initialises the DB if missing."""
    path = init_db(db_path)
    with _connect(path) as conn:
        yield conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a Row to dict (or None passthrough)."""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _payload_sha256(payload: dict[str, Any]) -> str:
    """Stable hash of a payload — for version-history diff anchoring."""
    import hashlib
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def upsert_record(
    *,
    content_id: str,
    record_type: str,
    lane: str,
    payload: dict[str, Any],
    state: str = "draft",
    actor_id: str = "system",
    actor_role: str = "system",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Insert or update a content record. New records start at the given state
    (default 'draft'); existing records preserve their state unless
    state_machine.transition() is called separately.

    Returns the resulting record row as a dict.
    """
    payload_json = json.dumps(payload, ensure_ascii=False)
    payload_sha = _payload_sha256(payload)
    meta = payload.get("metadata", {})
    now = _now()

    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM content_records WHERE content_id = ?", (content_id,)
        ).fetchone()

        if existing is None:
            # Insert new
            conn.execute(
                """
                INSERT INTO content_records
                    (content_id, record_type, lane, state, state_changed_at_utc,
                     payload_json, payload_sha256, source_unit_id, source_id,
                     subject, chapter_no, created_at_utc, updated_at_utc,
                     train_allowed, quality_status, version_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    content_id, record_type, lane, state, now,
                    payload_json, payload_sha, meta.get("source_unit_id"), meta.get("source_id"),
                    meta.get("subject"), meta.get("chapter_no"), now, now,
                    1 if meta.get("train_allowed") else 0,
                    meta.get("quality_status", "draft"),
                ),
            )
            # Write initial version
            conn.execute(
                """
                INSERT INTO content_versions
                    (content_id, version_number, payload_json, payload_sha256,
                     state, changed_by, change_reason, timestamp_utc)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (content_id, payload_json, payload_sha, state, actor_id,
                 "initial_registration", now),
            )
            # Record transition (None → state)
            conn.execute(
                """
                INSERT INTO state_transitions
                    (content_id, from_state, to_state, actor_id, actor_role,
                     reason, timestamp_utc, metadata_json)
                VALUES (?, NULL, ?, ?, ?, ?, ?, NULL)
                """,
                (content_id, state, actor_id, actor_role, "initial_registration", now),
            )
            new_row = conn.execute(
                "SELECT * FROM content_records WHERE content_id = ?", (content_id,)
            ).fetchone()
            return dict(new_row)

        # Existing — update payload + bump version if payload changed
        old_sha = existing["payload_sha256"]
        if payload_sha == old_sha:
            # No-op: payload unchanged. Just touch updated_at_utc.
            conn.execute(
                "UPDATE content_records SET updated_at_utc = ? WHERE content_id = ?",
                (now, content_id),
            )
            return dict(existing)

        new_version = int(existing["version_number"]) + 1
        conn.execute(
            """
            UPDATE content_records
            SET payload_json = ?, payload_sha256 = ?, updated_at_utc = ?,
                version_number = ?
            WHERE content_id = ?
            """,
            (payload_json, payload_sha, now, new_version, content_id),
        )
        conn.execute(
            """
            INSERT INTO content_versions
                (content_id, version_number, payload_json, payload_sha256,
                 state, changed_by, change_reason, timestamp_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (content_id, new_version, payload_json, payload_sha,
             existing["state"], actor_id, "payload_update", now),
        )
        updated = conn.execute(
            "SELECT * FROM content_records WHERE content_id = ?", (content_id,)
        ).fetchone()
        return dict(updated)


def get_record(content_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Return the current record row by content_id, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM content_records WHERE content_id = ?", (content_id,)
        ).fetchone()
        return row_to_dict(row)


def list_records(
    *,
    state: str | None = None,
    lane: str | None = None,
    subject: str | None = None,
    limit: int = 100,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List records filtered by optional state / lane / subject. Newest first."""
    clauses: list[str] = []
    params: list[Any] = []
    if state:
        clauses.append("state = ?")
        params.append(state)
    if lane:
        clauses.append("lane = ?")
        params.append(lane)
    if subject:
        clauses.append("subject = ?")
        params.append(subject)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT * FROM content_records
        {where}
        ORDER BY updated_at_utc DESC
        LIMIT ?
    """
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return rows_to_dicts(rows)


def count_by_state(db_path: Path | str | None = None) -> dict[str, int]:
    """Aggregate count per state — used by dashboard."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT state, COUNT(*) AS n FROM content_records GROUP BY state"
        ).fetchall()
        return {row["state"]: row["n"] for row in rows}


def count_by_lane(db_path: Path | str | None = None) -> dict[str, int]:
    """Aggregate count per lane."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT lane, COUNT(*) AS n FROM content_records GROUP BY lane"
        ).fetchall()
        return {row["lane"]: row["n"] for row in rows}
