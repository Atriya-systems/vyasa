"""CMS content quality dashboard — aggregate metrics for content ops + founder review.

This module is read-only against the SQLite catalog. Output is a single
``DashboardReport`` dict that downstream UIs (Streamlit, Markdown report,
JSON for a future Next.js admin panel) render as they prefer.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from aspireace_mocf.cms.comments import count_unresolved_flags
from aspireace_mocf.cms.queues import queue_summary
from aspireace_mocf.cms.storage import (
    _now,
    connect,
    count_by_lane,
    count_by_state,
)
from aspireace_mocf.utils.logging import get_logger

_log = get_logger(__name__)


def reviewer_throughput(
    days: int = 7,
    db_path=None,
) -> dict[str, dict[str, int]]:
    """Per-reviewer activity over the last N days: comments / approvals / flags.

    Returns: ``{reviewer_id: {comments: n, approvals: n, flags_raised: n,
    flags_resolved: n, queue_completed: n}}``.
    """
    since = (_dt.datetime.now(_dt.UTC) - _dt.timedelta(days=days)).isoformat()
    out: dict[str, dict[str, int]] = {}

    with connect(db_path) as conn:
        # Comments authored
        for row in conn.execute(
            """
            SELECT author_id, COUNT(*) AS n
            FROM comments
            WHERE timestamp_utc >= ?
            GROUP BY author_id
            """,
            (since,),
        ).fetchall():
            out.setdefault(row["author_id"], {})["comments"] = row["n"]

        # State transitions to senior_approved (approvals)
        for row in conn.execute(
            """
            SELECT actor_id, COUNT(*) AS n
            FROM state_transitions
            WHERE timestamp_utc >= ? AND to_state IN ('senior_approved', 'published')
            GROUP BY actor_id
            """,
            (since,),
        ).fetchall():
            out.setdefault(row["actor_id"], {})["approvals"] = row["n"]

        # Flags raised
        for row in conn.execute(
            """
            SELECT flagged_by, COUNT(*) AS n
            FROM accuracy_flags
            WHERE flagged_at_utc >= ?
            GROUP BY flagged_by
            """,
            (since,),
        ).fetchall():
            out.setdefault(row["flagged_by"], {})["flags_raised"] = row["n"]

        # Flags resolved
        for row in conn.execute(
            """
            SELECT resolved_by, COUNT(*) AS n
            FROM accuracy_flags
            WHERE resolved_at_utc >= ? AND resolved_by IS NOT NULL
            GROUP BY resolved_by
            """,
            (since,),
        ).fetchall():
            if row["resolved_by"]:
                out.setdefault(row["resolved_by"], {})["flags_resolved"] = row["n"]

        # Queue entries completed
        for row in conn.execute(
            """
            SELECT completed_by, COUNT(*) AS n
            FROM review_queues
            WHERE completed_at_utc >= ? AND completed_by IS NOT NULL
            GROUP BY completed_by
            """,
            (since,),
        ).fetchall():
            if row["completed_by"]:
                out.setdefault(row["completed_by"], {})["queue_completed"] = row["n"]

    return out


def flag_age_distribution(db_path=None) -> dict[str, int]:
    """Bucket unresolved flags by age. Used to surface 'we have 12 critical
    flags unresolved for >7 days' patterns."""
    now_dt = _dt.datetime.now(_dt.UTC)
    buckets: dict[str, int] = {
        "lt_1d": 0,
        "lt_7d": 0,
        "lt_30d": 0,
        "gte_30d": 0,
    }
    with connect(db_path) as conn:
        for row in conn.execute(
            "SELECT flagged_at_utc FROM accuracy_flags WHERE resolved_at_utc IS NULL"
        ).fetchall():
            ts = _dt.datetime.fromisoformat(row["flagged_at_utc"].replace("Z", "+00:00"))
            age_days = (now_dt - ts).days
            if age_days < 1:
                buckets["lt_1d"] += 1
            elif age_days < 7:
                buckets["lt_7d"] += 1
            elif age_days < 30:
                buckets["lt_30d"] += 1
            else:
                buckets["gte_30d"] += 1
    return buckets


def coverage_matrix(db_path=None) -> dict[str, dict[str, int]]:
    """Per-subject x per-lane record count. The 'what's covered' view."""
    out: dict[str, dict[str, int]] = {}
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT subject, lane, COUNT(*) AS n
            FROM content_records
            WHERE subject IS NOT NULL
            GROUP BY subject, lane
            """
        ).fetchall()
        for row in rows:
            subject = row["subject"]
            out.setdefault(subject, {})[row["lane"]] = row["n"]
    return out


def dashboard_report(db_path=None) -> dict[str, Any]:
    """One-call summary suitable for rendering as a top-of-page dashboard."""
    report = {
        "generated_at_utc": _now(),
        "records_by_state": count_by_state(db_path),
        "records_by_lane": count_by_lane(db_path),
        "unresolved_flags_by_type": count_unresolved_flags(db_path),
        "flag_age_distribution": flag_age_distribution(db_path),
        "queue_summary": queue_summary(db_path),
        "reviewer_throughput_7d": reviewer_throughput(7, db_path),
        "coverage_matrix": coverage_matrix(db_path),
    }
    return report


def render_markdown_summary(report: dict[str, Any]) -> str:
    """Render dashboard_report as a human-readable Markdown summary."""
    lines: list[str] = [
        "# Vyasa CMS — content quality dashboard",
        "",
        f"_Generated at: {report['generated_at_utc']}_",
        "",
        "## Records by state",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state, n in sorted(report["records_by_state"].items()):
        lines.append(f"| {state} | {n} |")
    lines.append("")

    lines.append("## Records by lane")
    lines.append("")
    lines.append("| Lane | Count |")
    lines.append("|---|---:|")
    for lane, n in sorted(report["records_by_lane"].items()):
        lines.append(f"| {lane} | {n} |")
    lines.append("")

    lines.append("## Unresolved flags by type")
    lines.append("")
    if report["unresolved_flags_by_type"]:
        lines.append("| Flag type | Count |")
        lines.append("|---|---:|")
        for ft, n in sorted(report["unresolved_flags_by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"| {ft} | {n} |")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Flag age distribution (unresolved)")
    lines.append("")
    lines.append("| Age bucket | Count |")
    lines.append("|---|---:|")
    age_labels = {
        "lt_1d": "< 1 day",
        "lt_7d": "1-7 days",
        "lt_30d": "8-30 days",
        "gte_30d": "> 30 days",
    }
    for key in ["lt_1d", "lt_7d", "lt_30d", "gte_30d"]:
        lines.append(f"| {age_labels[key]} | {report['flag_age_distribution'].get(key, 0)} |")
    lines.append("")

    lines.append("## Queue summary")
    lines.append("")
    if report["queue_summary"]:
        lines.append("| Queue | Pending | In review | Overdue |")
        lines.append("|---|---:|---:|---:|")
        for qt, s in sorted(report["queue_summary"].items()):
            lines.append(f"| {qt} | {s['pending']} | {s['in_review']} | {s['overdue']} |")
    else:
        lines.append("_All queues empty._")
    lines.append("")

    lines.append("## Reviewer throughput (last 7 days)")
    lines.append("")
    if report["reviewer_throughput_7d"]:
        lines.append("| Reviewer | Comments | Approvals | Flags raised | Flags resolved | Queue completed |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for reviewer_id, stats in sorted(report["reviewer_throughput_7d"].items()):
            lines.append(
                f"| {reviewer_id} | "
                f"{stats.get('comments', 0)} | "
                f"{stats.get('approvals', 0)} | "
                f"{stats.get('flags_raised', 0)} | "
                f"{stats.get('flags_resolved', 0)} | "
                f"{stats.get('queue_completed', 0)} |"
            )
    else:
        lines.append("_No activity in the last 7 days._")
    lines.append("")

    lines.append("## Coverage matrix (records per subject x lane)")
    lines.append("")
    if report["coverage_matrix"]:
        all_lanes = sorted({lane for v in report["coverage_matrix"].values() for lane in v.keys()})
        lines.append("| Subject | " + " | ".join(all_lanes) + " |")
        lines.append("|---|" + "|".join(["---:"] * len(all_lanes)) + "|")
        for subj, lane_counts in sorted(report["coverage_matrix"].items()):
            row = f"| {subj} | " + " | ".join(str(lane_counts.get(l, 0)) for l in all_lanes) + " |"
            lines.append(row)
    else:
        lines.append("_No records registered._")
    lines.append("")

    return "\n".join(lines)
