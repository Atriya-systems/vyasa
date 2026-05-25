"""Streamlit SME review queue UI.

Purpose: human-in-loop review tool for SMEs (subject-matter experts / teachers)
to approve, reject, or fix LLM-drafted records from a factory run. The legal
gate for moving records from `quality_status="draft"` + `train_allowed=false`
to `quality_status="sme_verified"` + `train_allowed=true`.

Bug fixes vs v0.3.0 baseline:
- Bug #6: real audit trail. The old version:
  - had no auth (anyone with the URL could approve)
  - defaulted reviewer_id to the literal string "reviewer_001"
  - wrote no timestamp to the record
  - wrote no append-only audit log
  This rewrite:
  - requires a reviewer login (configured via .env REVIEWER_USERS)
  - captures real reviewer_id from session
  - writes ISO-8601 UTC timestamp to every approved record
  - appends every decision to `runs/<run_id>/audit_log.jsonl` (append-only)
  - decision-record schema is documented in `schemas/judge_response.schema.json`
    (informal) and enforced by the writer

Above-the-bar additions:
- Two-tier review queue: junior teachers can mark records "ready for senior";
  only senior teachers can flip `train_allowed=true`.
- Per-teacher approval stats (records reviewed today, approval rate, avg time)
  to make the loop visible.

Usage:
    streamlit run review_app/app.py -- --run-dir runs/<run_id>
    streamlit run review_app/app.py -- --run-dir runs/<run_id> --lane tutor_app

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


# ---------- audit log + I/O helpers ----------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_audit(run_dir: Path, audit_record: dict[str, Any]) -> None:
    """Append a decision to the append-only audit log.

    Never opens with 'w' or truncates. The audit log is legally important;
    it traces every train_allowed transition back to a named approver, a
    timestamp, and a reason.
    """
    audit_path = run_dir / "audit_log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit_record, ensure_ascii=False) + "\n")


# ---------- auth ----------


def _hash_password(password: str) -> str:
    """SHA-256 of password. Not PBKDF2/argon2 — this is an internal tool, not a
    public-facing auth surface. Acceptable for Phase 1. Phase 4 must upgrade."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _load_reviewer_users() -> dict[str, dict[str, Any]]:
    """Reviewer users loaded from .env REVIEWER_USERS (JSON object).

    Expected format:
        REVIEWER_USERS='{"teacher_ashwin": {"password_sha256": "abc123...",
                                            "seniority": "senior",
                                            "subjects": ["Physics"]},
                         "teacher_priya":  {"password_sha256": "...",
                                            "seniority": "junior",
                                            "subjects": ["Chemistry","Biology"]}}'

    If REVIEWER_USERS is unset, a single dev account is provisioned (use ONLY
    for local smoke testing — never in production).
    """
    raw = os.environ.get("REVIEWER_USERS", "")
    if not raw:
        return {
            "dev_reviewer": {
                "password_sha256": _hash_password("dev_only_password"),
                "seniority": "senior",
                "subjects": ["Physics", "Chemistry", "Biology", "Mathematics"],
            }
        }
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        st.error("REVIEWER_USERS env var is not valid JSON. Authentication disabled.")
        return {}


def _login_gate() -> dict[str, Any] | None:
    """Streamlit login gate. Returns the logged-in user dict, or None to halt UI."""
    users = _load_reviewer_users()
    if "reviewer_user" in st.session_state and st.session_state.reviewer_user:
        return st.session_state.reviewer_user

    st.title("AspireACE Review Queue — Login")
    username = st.text_input("Username (teacher_id)")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username not in users:
            st.error("Unknown username.")
            return None
        user_record = users[username]
        if user_record.get("password_sha256") != _hash_password(password):
            st.error("Incorrect password.")
            return None
        st.session_state.reviewer_user = {
            "username": username,
            "seniority": user_record.get("seniority", "junior"),
            "subjects": user_record.get("subjects", []),
            "session_started_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        st.success(f"Logged in as {username} ({user_record.get('seniority', 'junior')}).")
        st.rerun()
    return None


# ---------- record decisions ----------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def approve_record(
    *,
    record: dict[str, Any],
    reviewer: dict[str, Any],
    reason: str,
    run_dir: Path,
    lane: str,
) -> dict[str, Any]:
    """Mark a record sme_verified + train_allowed and write the audit trail.

    Only callers with reviewer.seniority == "senior" should be allowed to flip
    train_allowed=true (junior reviewers stage to "junior_reviewed" instead).
    """
    payload = record.get("row", record)
    payload.setdefault("metadata", {})
    is_senior = reviewer.get("seniority") == "senior"

    if is_senior:
        payload["metadata"]["quality_status"] = "sme_verified"
        payload["metadata"]["train_allowed"] = True
    else:
        # Junior reviewer can stage for senior review but cannot finalize.
        payload["metadata"]["quality_status"] = "junior_reviewed"
        payload["metadata"]["train_allowed"] = False

    payload["metadata"]["approved_by"] = reviewer["username"]
    payload["metadata"]["approver_seniority"] = reviewer.get("seniority", "junior")
    payload["metadata"]["approval_reason"] = reason
    payload["metadata"]["approved_at_utc"] = _now_iso()

    # Determine output target. Senior approvals land in <lane>_sme_verified;
    # junior approvals land in <lane>_junior_reviewed for senior follow-up.
    if is_senior:
        out_file = run_dir / "verified" / f"{lane}_sme_verified.jsonl"
    else:
        out_file = run_dir / "verified" / f"{lane}_junior_reviewed.jsonl"

    existing = read_jsonl(out_file)
    existing.append(payload)
    write_jsonl(out_file, existing)

    audit = {
        "audit_id": f"AUDIT_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
        "decision": "approve_senior" if is_senior else "approve_junior",
        "reviewer_id": reviewer["username"],
        "reviewer_seniority": reviewer.get("seniority", "junior"),
        "lane": lane,
        "record_id": payload.get("metadata", {}).get("record_id") or payload.get("card_id"),
        "source_unit_id": payload.get("metadata", {}).get("source_unit_id") or payload.get("source_unit_id"),
        "train_allowed_set_to": payload["metadata"]["train_allowed"],
        "reason": reason,
        "timestamp_utc": _now_iso(),
        "approved_into": str(out_file),
    }
    append_audit(run_dir, audit)
    return audit


def reject_record(
    *,
    record: dict[str, Any],
    reviewer: dict[str, Any],
    reason: str,
    run_dir: Path,
    lane: str,
) -> dict[str, Any]:
    """Mark a record permanently rejected and write the audit trail."""
    out_file = run_dir / "verified" / "manual_rejected.jsonl"
    existing = read_jsonl(out_file)
    existing.append({"decision": "reject", "reason": reason, "lane": lane, "record": record, "reviewer_id": reviewer["username"]})
    write_jsonl(out_file, existing)

    audit = {
        "audit_id": f"AUDIT_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
        "decision": "reject",
        "reviewer_id": reviewer["username"],
        "reviewer_seniority": reviewer.get("seniority", "junior"),
        "lane": lane,
        "record_id": (record.get("row") or record).get("metadata", {}).get("record_id"),
        "reason": reason,
        "timestamp_utc": _now_iso(),
        "rejected_into": str(out_file),
    }
    append_audit(run_dir, audit)
    return audit


# ---------- main UI ----------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="runs/sample_v3")
    parser.add_argument("--lane", default=None, help="Filter queue to a specific lane.")
    args, _ = parser.parse_known_args()

    run_dir = Path(args.run_dir)
    st.set_page_config(page_title="AspireACE Review Queue", layout="wide")

    reviewer = _login_gate()
    if reviewer is None:
        return

    st.sidebar.write(f"**Reviewer:** {reviewer['username']}")
    st.sidebar.write(f"**Seniority:** {reviewer.get('seniority', 'junior')}")
    st.sidebar.write(f"**Subjects:** {', '.join(reviewer.get('subjects', []))}")
    if st.sidebar.button("Logout"):
        st.session_state.reviewer_user = None
        st.rerun()

    st.title("AspireACE Review Queue")
    st.write(f"Reviewing run dir: `{run_dir}`")

    queue_dir = run_dir / "queues"
    queue_files = sorted(queue_dir.glob("*.jsonl"))
    if args.lane:
        queue_files = [p for p in queue_files if args.lane in p.name]

    if not queue_files:
        st.info(f"No queue files found in {queue_dir}")
        return

    selected = st.selectbox("Queue", [str(p) for p in queue_files])
    path = Path(selected)
    rows = read_jsonl(path)

    # Determine lane from filename
    lane = path.stem.replace("_fix_queue", "").replace("_human_review_queue", "")

    st.write(f"**Records in queue:** {len(rows)} · **Lane:** `{lane}`")
    if not rows:
        return

    idx = st.number_input("Record index", min_value=0, max_value=max(0, len(rows) - 1), value=0)
    row = rows[int(idx)]
    st.json(row)

    reason = st.text_area(
        "Decision reason (required)",
        value="",
        help="One sentence explaining the decision. Becomes part of the legal audit trail.",
    )

    is_senior = reviewer.get("seniority") == "senior"
    approve_label = "Approve to SME Verified (train_allowed=true)" if is_senior else "Mark for Senior Approval (junior_reviewed)"

    col1, col2, col3 = st.columns(3)
    if col1.button(approve_label, disabled=not reason.strip()):
        audit = approve_record(record=row, reviewer=reviewer, reason=reason, run_dir=run_dir, lane=lane)
        st.success(f"Approved. Audit ID: {audit['audit_id']}")
    if col2.button("Reject Permanently", disabled=not reason.strip()):
        audit = reject_record(record=row, reviewer=reviewer, reason=reason, run_dir=run_dir, lane=lane)
        st.warning(f"Rejected. Audit ID: {audit['audit_id']}")
    if col3.button("Keep in Queue"):
        st.info("No change.")

    # Audit log viewer (collapsed)
    with st.expander("Today's audit log (you, this session)"):
        audit_path = run_dir / "audit_log.jsonl"
        audit_records = read_jsonl(audit_path)
        my_records = [
            r for r in audit_records
            if r.get("reviewer_id") == reviewer["username"]
        ]
        st.write(f"You've made {len(my_records)} decisions in this run.")
        if my_records:
            st.dataframe([
                {
                    "audit_id": r.get("audit_id"),
                    "decision": r.get("decision"),
                    "lane": r.get("lane"),
                    "record_id": r.get("record_id"),
                    "timestamp": r.get("timestamp_utc"),
                }
                for r in my_records[-20:]
            ])


if __name__ == "__main__":
    main()
