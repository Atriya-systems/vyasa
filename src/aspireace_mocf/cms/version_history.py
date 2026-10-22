"""CMS version history — per-record immutable payload snapshots + diff helper.

Every payload mutation (via storage.upsert_record) writes a new row into
content_versions with monotonically-increasing version_number. This module
provides the read-side API plus a simple diff helper.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import difflib
import json
from typing import Any

from aspireace_mocf.cms.storage import connect
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


def get_versions(content_id: str, db_path=None) -> list[dict[str, Any]]:
    """All versions of a content record, newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM content_versions
            WHERE content_id = ?
            ORDER BY version_number DESC
            """,
            (content_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_version(
    content_id: str,
    version_number: int,
    db_path=None,
) -> dict[str, Any] | None:
    """One specific version of a record."""
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM content_versions
            WHERE content_id = ? AND version_number = ?
            """,
            (content_id, version_number),
        ).fetchone()
        return dict(row) if row else None


def latest_version(content_id: str, db_path=None) -> dict[str, Any] | None:
    """Most recent version of a record (matches content_records current state)."""
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM content_versions
            WHERE content_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (content_id,),
        ).fetchone()
        return dict(row) if row else None


def diff_versions(
    content_id: str,
    from_version: int,
    to_version: int,
    db_path=None,
) -> str:
    """Return a unified-diff between two versions of a record. Useful for
    review UI 'see what changed' view.

    Diff is over the JSON-stringified payloads (pretty-printed for human
    readability), not the binary payload_sha256.
    """
    a = get_version(content_id, from_version, db_path)
    b = get_version(content_id, to_version, db_path)
    if a is None or b is None:
        raise ValueError(
            f"Cannot diff: missing version. "
            f"from={from_version} (found={a is not None}) "
            f"to={to_version} (found={b is not None})"
        )
    a_str = json.dumps(json.loads(a["payload_json"]), indent=2, ensure_ascii=False, sort_keys=True).splitlines(keepends=True)
    b_str = json.dumps(json.loads(b["payload_json"]), indent=2, ensure_ascii=False, sort_keys=True).splitlines(keepends=True)
    diff = difflib.unified_diff(
        a_str, b_str,
        fromfile=f"v{from_version}",
        tofile=f"v{to_version}",
        n=3,
    )
    return "".join(diff)


def count_versions(content_id: str, db_path=None) -> int:
    """Number of versions a record has accumulated."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM content_versions WHERE content_id = ?",
            (content_id,),
        ).fetchone()
        return int(row["n"]) if row else 0


def rollback_to_version(
    content_id: str,
    target_version: int,
    *,
    actor_id: str,
    reason: str,
    db_path=None,
) -> dict[str, Any]:
    """Restore a record's payload to a previous version. The restoration itself
    creates a new version (so the timeline stays append-only) — it doesn't
    delete the intervening history.

    Returns the new version row.
    """
    target = get_version(content_id, target_version, db_path)
    if target is None:
        raise ValueError(
            f"Cannot rollback {content_id!r} — version {target_version} not found."
        )
    # Re-upsert with the old payload. This bumps version_number and creates
    # an audit trail in content_versions.
    from aspireace_mocf.cms.storage import upsert_record  # local import to avoid cycle

    payload = json.loads(target["payload_json"])
    record_state = target["state"]
    # Get the current record to know record_type + lane
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT record_type, lane FROM content_records WHERE content_id = ?",
            (content_id,),
        ).fetchone()
        if cur is None:
            raise ValueError(f"content_id {content_id!r} not in catalog.")
        record_type = cur["record_type"]
        lane = cur["lane"]

    updated = upsert_record(
        content_id=content_id,
        record_type=record_type,
        lane=lane,
        payload=payload,
        state=record_state,
        actor_id=actor_id,
        actor_role="admin",
        db_path=db_path,
    )
    _log.info(
        "cms_version_rollback",
        content_id=content_id,
        target_version=target_version,
        new_version=updated["version_number"],
        actor_id=actor_id,
        reason=reason,
    )
    return updated
