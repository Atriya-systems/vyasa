"""CMS comments — threaded review comments + accuracy flags per content record.

Two related capabilities live here:
1. Threaded comments (parent_comment_id supports replies)
2. Typed accuracy flags (factual_error / pedagogical_issue / formula_error / etc.)

Both write to the SQLite catalog set up by cms.storage. Append-only by
default — comments + flags are never deleted, only resolved.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from aspireace_mocf.cms.storage import _now, connect
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


class FlagType(str, Enum):
    FACTUAL_ERROR = "factual_error"
    PEDAGOGICAL_ISSUE = "pedagogical_issue"
    UNCLEAR_WORDING = "unclear_wording"
    FORMULA_ERROR = "formula_error"
    LANGUAGE_ISSUE = "language_issue"
    IMAGE_ISSUE = "image_issue"
    SOLUTION_ERROR = "solution_error"
    LEVEL_INAPPROPRIATE = "level_inappropriate"


class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Severity that triggers automatic state transition to 'flagged'
AUTO_FLAG_SEVERITIES: frozenset[str] = frozenset({FlagSeverity.WARNING, FlagSeverity.CRITICAL})


# ---------- comments ----------


def add_comment(
    *,
    content_id: str,
    author_id: str,
    author_role: str,
    body: str,
    parent_comment_id: int | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Append a comment to a content record's thread. Reply via parent_comment_id."""
    if not body.strip():
        raise ValueError("Comment body cannot be empty.")
    now = _now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO comments
                (content_id, parent_comment_id, author_id, author_role, body, timestamp_utc, resolved)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (content_id, parent_comment_id, author_id, author_role, body, now),
        )
        comment_id = cur.lastrowid
        row = conn.execute("SELECT * FROM comments WHERE comment_id = ?", (comment_id,)).fetchone()
    _log.info(
        "cms_comment_added",
        content_id=content_id,
        comment_id=comment_id,
        author_id=author_id,
        reply_to=parent_comment_id,
    )
    return dict(row)


def get_comments(content_id: str, db_path=None) -> list[dict[str, Any]]:
    """All comments for one record, oldest first (thread-display order)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM comments WHERE content_id = ? ORDER BY timestamp_utc ASC",
            (content_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_comment(
    comment_id: int,
    *,
    resolved_by: str,
    db_path=None,
) -> dict[str, Any] | None:
    """Mark a comment resolved. Doesn't delete it. Returns the updated row."""
    now = _now()
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE comments SET resolved = 1, resolved_at_utc = ?, resolved_by = ? WHERE comment_id = ?",
            (now, resolved_by, comment_id),
        )
        row = conn.execute("SELECT * FROM comments WHERE comment_id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None


# ---------- flags ----------


def add_flag(
    *,
    content_id: str,
    flag_type: str,
    severity: str,
    flagged_by: str,
    flagged_by_role: str,
    reason: str = "",
    db_path=None,
) -> dict[str, Any]:
    """Raise an accuracy flag against a content record.

    If severity is WARNING or CRITICAL, the caller should follow up with
    state_machine.transition(content_id, to_state='flagged', ...) — the
    flagging is a content concern; the state transition is a workflow
    concern. We keep them decoupled so an INFO-severity flag (e.g. 'minor
    typo') doesn't auto-trigger an expensive flagged-state cycle.
    """
    if flag_type not in {f.value for f in FlagType}:
        raise ValueError(
            f"Unknown flag_type {flag_type!r}. Allowed: {[f.value for f in FlagType]}"
        )
    if severity not in {s.value for s in FlagSeverity}:
        raise ValueError(
            f"Unknown severity {severity!r}. Allowed: {[s.value for s in FlagSeverity]}"
        )
    now = _now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO accuracy_flags
                (content_id, flag_type, severity, flagged_by, flagged_by_role,
                 flag_reason, flagged_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (content_id, flag_type, severity, flagged_by, flagged_by_role, reason, now),
        )
        flag_id = cur.lastrowid
        row = conn.execute("SELECT * FROM accuracy_flags WHERE flag_id = ?", (flag_id,)).fetchone()
    _log.info(
        "cms_flag_raised",
        content_id=content_id,
        flag_id=flag_id,
        flag_type=flag_type,
        severity=severity,
        flagged_by=flagged_by,
    )
    return dict(row)


def get_flags(
    content_id: str,
    *,
    only_unresolved: bool = False,
    db_path=None,
) -> list[dict[str, Any]]:
    """Flags for one record. Newest first."""
    with connect(db_path) as conn:
        if only_unresolved:
            rows = conn.execute(
                """
                SELECT * FROM accuracy_flags
                WHERE content_id = ? AND resolved_at_utc IS NULL
                ORDER BY flagged_at_utc DESC
                """,
                (content_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM accuracy_flags
                WHERE content_id = ?
                ORDER BY flagged_at_utc DESC
                """,
                (content_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def resolve_flag(
    flag_id: int,
    *,
    resolved_by: str,
    resolution_action: str,
    db_path=None,
) -> dict[str, Any] | None:
    """Mark a flag resolved with a recorded action (e.g. 'fixed the formula',
    'rejected as not a real issue', 'escalated to senior')."""
    now = _now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE accuracy_flags
            SET resolved_at_utc = ?, resolved_by = ?, resolution_action = ?
            WHERE flag_id = ?
            """,
            (now, resolved_by, resolution_action, flag_id),
        )
        row = conn.execute("SELECT * FROM accuracy_flags WHERE flag_id = ?", (flag_id,)).fetchone()
        return dict(row) if row else None


def count_unresolved_flags(db_path=None) -> dict[str, int]:
    """Aggregate count of unresolved flags by flag_type. Dashboard signal."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT flag_type, COUNT(*) AS n
            FROM accuracy_flags
            WHERE resolved_at_utc IS NULL
            GROUP BY flag_type
            """
        ).fetchall()
        return {row["flag_type"]: row["n"] for row in rows}
