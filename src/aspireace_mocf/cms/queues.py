"""CMS needs-review queues — assignment + SLA + prioritisation.

5 queue types per canonical §Q5:
- new_author_submission: source just submitted, awaiting machine validation
- ai_generated_pending: factory-generated content, awaiting SME review
- student_flagged: flagged via accuracy_flag from student-facing surface
- license_recheck: licensed reference content due for periodic license review
- accuracy_flag_triage: high-severity flags that need senior triage

Each entry has: assigned_to (optional), priority, SLA deadline, state.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any

from aspireace_mocf.cms.storage import _now, connect
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


class QueueType(str, Enum):
    NEW_AUTHOR_SUBMISSION = "new_author_submission"
    AI_GENERATED_PENDING = "ai_generated_pending"
    STUDENT_FLAGGED = "student_flagged"
    LICENSE_RECHECK = "license_recheck"
    ACCURACY_FLAG_TRIAGE = "accuracy_flag_triage"


class QueuePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class QueueState(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"


# Default SLA deadlines per queue_type, in hours.
DEFAULT_SLA_HOURS: dict[str, int] = {
    QueueType.NEW_AUTHOR_SUBMISSION: 72,
    QueueType.AI_GENERATED_PENDING: 24 * 7,    # weekly review cadence
    QueueType.STUDENT_FLAGGED: 48,
    QueueType.LICENSE_RECHECK: 24 * 30,        # monthly
    QueueType.ACCURACY_FLAG_TRIAGE: 24,        # critical — 1 day
}


def _sla_deadline(queue_type: str, hours_override: int | None = None) -> str:
    """Compute SLA deadline timestamp from now + N hours."""
    hours = hours_override if hours_override is not None else DEFAULT_SLA_HOURS.get(queue_type, 72)
    deadline = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=hours)
    return deadline.isoformat()


def enqueue(
    *,
    content_id: str,
    queue_type: str,
    priority: str = "normal",
    assigned_to: str | None = None,
    sla_hours: int | None = None,
    notes: str = "",
    db_path=None,
) -> dict[str, Any]:
    """Add a content_id to a review queue."""
    if queue_type not in {q.value for q in QueueType}:
        raise ValueError(f"Unknown queue_type {queue_type!r}. Allowed: {[q.value for q in QueueType]}")
    if priority not in {p.value for p in QueuePriority}:
        raise ValueError(f"Unknown priority {priority!r}. Allowed: {[p.value for p in QueuePriority]}")
    now = _now()
    sla = _sla_deadline(queue_type, sla_hours)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO review_queues
                (queue_type, content_id, assigned_to, enqueued_at_utc,
                 sla_deadline_utc, priority, state, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (queue_type, content_id, assigned_to, now, sla, priority, notes),
        )
        queue_id = cur.lastrowid
        row = conn.execute("SELECT * FROM review_queues WHERE queue_id = ?", (queue_id,)).fetchone()
    _log.info(
        "cms_enqueue",
        queue_id=queue_id,
        content_id=content_id,
        queue_type=queue_type,
        priority=priority,
        assigned_to=assigned_to,
    )
    return dict(row)


def list_queue(
    queue_type: str | None = None,
    *,
    assigned_to: str | None = None,
    state: str | None = "pending",
    priority: str | None = None,
    overdue_only: bool = False,
    limit: int = 50,
    db_path=None,
) -> list[dict[str, Any]]:
    """Filter queue entries. Sorted by priority desc, then SLA asc (most overdue first)."""
    clauses: list[str] = []
    params: list[Any] = []
    if queue_type:
        clauses.append("queue_type = ?")
        params.append(queue_type)
    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    if state:
        clauses.append("state = ?")
        params.append(state)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if overdue_only:
        clauses.append("sla_deadline_utc < ?")
        params.append(_now())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT * FROM review_queues
        {where}
        ORDER BY
            CASE priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            sla_deadline_utc ASC
        LIMIT ?
    """
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def assign_queue_entry(
    queue_id: int,
    *,
    assigned_to: str,
    db_path=None,
) -> dict[str, Any] | None:
    """Assign a queue entry to a reviewer."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE review_queues SET assigned_to = ?, state = 'in_review' WHERE queue_id = ?",
            (assigned_to, queue_id),
        )
        row = conn.execute("SELECT * FROM review_queues WHERE queue_id = ?", (queue_id,)).fetchone()
    _log.info("cms_queue_assigned", queue_id=queue_id, assigned_to=assigned_to)
    return dict(row) if row else None


def complete_queue_entry(
    queue_id: int,
    *,
    completed_by: str,
    notes: str = "",
    db_path=None,
) -> dict[str, Any] | None:
    """Mark a queue entry completed. Records completion timestamp + actor."""
    now = _now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE review_queues
            SET state = 'completed', completed_at_utc = ?, completed_by = ?,
                notes = COALESCE(?, notes)
            WHERE queue_id = ?
            """,
            (now, completed_by, notes if notes else None, queue_id),
        )
        row = conn.execute("SELECT * FROM review_queues WHERE queue_id = ?", (queue_id,)).fetchone()
    _log.info("cms_queue_completed", queue_id=queue_id, completed_by=completed_by)
    return dict(row) if row else None


def queue_summary(db_path=None) -> dict[str, dict[str, int]]:
    """Per-queue-type summary: pending count + in_review count + overdue count.

    Used by the quality dashboard."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT queue_type,
                   SUM(CASE WHEN state = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN state = 'in_review' THEN 1 ELSE 0 END) AS in_review,
                   SUM(CASE WHEN state IN ('pending', 'in_review')
                            AND sla_deadline_utc < ?
                            THEN 1 ELSE 0 END) AS overdue
            FROM review_queues
            GROUP BY queue_type
            """,
            (_now(),),
        ).fetchall()
        return {
            row["queue_type"]: {
                "pending": int(row["pending"] or 0),
                "in_review": int(row["in_review"] or 0),
                "overdue": int(row["overdue"] or 0),
            }
            for row in rows
        }
