"""CMS batch rollback — Q7 protocol for un-doing a bad ingest batch.

When a factory run produces a batch of records that turn out to be
systemically bad (LLM hallucination wave, schema drift, wrong source
material), we need to:
1. Quarantine every record in that batch (transition state → flagged)
2. Optionally retire each one (terminal state)
3. Preserve the audit trail so 'what we rolled back, when, who, why' is recoverable

Batches are tracked in ``content_batches``. Every CMS register call should
associate the imported records with a batch_id for rollback addressability.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import json
from typing import Any

from aspireace_mocf.cms.state_machine import transition
from aspireace_mocf.cms.storage import _now, connect
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


def register_batch(
    *,
    batch_id: str,
    description: str,
    run_id: str | None,
    record_ids: list[str],
    db_path=None,
) -> dict[str, Any]:
    """Register a content batch in the catalog. Idempotent on batch_id."""
    now = _now()
    record_ids_json = json.dumps(record_ids, ensure_ascii=False)
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM content_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if existing is not None:
            _log.info("cms_batch_already_registered", batch_id=batch_id)
            return dict(existing)
        conn.execute(
            """
            INSERT INTO content_batches
                (batch_id, description, run_id, created_at_utc,
                 record_count, record_ids_json, rollback_state)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (batch_id, description, run_id, now, len(record_ids), record_ids_json),
        )
        row = conn.execute(
            "SELECT * FROM content_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
    _log.info(
        "cms_batch_registered",
        batch_id=batch_id,
        record_count=len(record_ids),
        run_id=run_id,
    )
    return dict(row)


def list_batches(
    *,
    rollback_state: str | None = None,
    run_id: str | None = None,
    db_path=None,
) -> list[dict[str, Any]]:
    """List batches, optionally filtered."""
    clauses: list[str] = []
    params: list[Any] = []
    if rollback_state:
        clauses.append("rollback_state = ?")
        params.append(rollback_state)
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM content_batches {where} ORDER BY created_at_utc DESC"
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def rollback_batch(
    batch_id: str,
    *,
    actor_id: str,
    actor_role: str,
    reason: str,
    target_state: str = "flagged",
    db_path=None,
) -> dict[str, Any]:
    """Rollback a batch: walk every record_id in the batch and transition each
    to ``target_state`` (default 'flagged').

    ``target_state`` of ``retired`` permanently removes the records from the
    active catalog; ``flagged`` quarantines them pending review. Use 'flagged'
    by default — it's reversible.

    Returns a summary dict with batch metadata + per-record success/failure.
    """
    if target_state not in {"flagged", "retired"}:
        raise ValueError(
            f"target_state must be 'flagged' or 'retired', got {target_state!r}"
        )

    with connect(db_path) as conn:
        batch_row = conn.execute(
            "SELECT * FROM content_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if batch_row is None:
            raise ValueError(f"batch_id {batch_id!r} not found.")
        if batch_row["rollback_state"] == "rolled_back":
            _log.warning("cms_batch_already_rolled_back", batch_id=batch_id)
            return {
                "batch_id": batch_id,
                "rollback_state": "rolled_back",
                "note": "Batch was already rolled back.",
                "rollback_at_utc": batch_row["rollback_at_utc"],
            }
        record_ids = json.loads(batch_row["record_ids_json"])

    success: list[str] = []
    failed: list[dict[str, Any]] = []
    for content_id in record_ids:
        try:
            transition(
                content_id,
                to_state=target_state,
                actor_id=actor_id,
                actor_role=actor_role,
                reason=f"batch_rollback: {reason} (batch_id={batch_id})",
                metadata={"batch_id": batch_id, "rollback_target": target_state},
                db_path=db_path,
            )
            success.append(content_id)
        except Exception as exc:
            failed.append({"content_id": content_id, "error": str(exc)})
            _log.warning(
                "cms_batch_rollback_record_failed",
                batch_id=batch_id,
                content_id=content_id,
                error=str(exc),
            )

    now = _now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE content_batches
            SET rollback_state = 'rolled_back',
                rollback_at_utc = ?,
                rollback_actor = ?,
                rollback_reason = ?
            WHERE batch_id = ?
            """,
            (now, actor_id, reason, batch_id),
        )

    _log.info(
        "cms_batch_rolled_back",
        batch_id=batch_id,
        actor_id=actor_id,
        target_state=target_state,
        success_count=len(success),
        failed_count=len(failed),
    )
    return {
        "batch_id": batch_id,
        "rollback_state": "rolled_back",
        "rollback_at_utc": now,
        "actor_id": actor_id,
        "target_state": target_state,
        "success_count": len(success),
        "failed_count": len(failed),
        "failed_records": failed,
    }


def get_batch(batch_id: str, db_path=None) -> dict[str, Any] | None:
    """Single batch metadata + record ID list."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM content_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["record_ids"] = json.loads(result["record_ids_json"])
        return result
