from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import streamlit as st


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="runs/sample_v3")
    args, _ = parser.parse_known_args()

    run_dir = Path(args.run_dir)
    st.set_page_config(page_title="AspireACE Review Queue", layout="wide")
    st.title("AspireACE ModelOps + ContentOps Review Queue")

    queue_dir = run_dir / "queues"
    verified_dir = run_dir / "verified"
    queue_files = sorted(queue_dir.glob("*.jsonl"))

    if not queue_files:
        st.info(f"No queue files found in {queue_dir}")
        return

    selected = st.selectbox("Queue", [str(p) for p in queue_files])
    path = Path(selected)
    rows = read_jsonl(path)

    st.write(f"Records: {len(rows)}")
    if not rows:
        return

    idx = st.number_input("Index", min_value=0, max_value=len(rows)-1, value=0)
    row = rows[idx]
    st.json(row)

    approver = st.text_input("Reviewer ID", value="reviewer_001")
    reason = st.text_area("Decision reason", value="Reviewed and approved.")

    col1, col2, col3 = st.columns(3)
    if col1.button("Approve to SME Verified"):
        record = row.get("row", row)
        record.setdefault("metadata", {})
        record["metadata"]["quality_status"] = "sme_verified"
        record["metadata"]["train_allowed"] = True
        record["metadata"]["approved_by"] = approver
        record["metadata"]["approval_reason"] = reason
        out = verified_dir / "manual_sme_verified.jsonl"
        existing = read_jsonl(out)
        existing.append(record)
        write_jsonl(out, existing)
        st.success(f"Approved into {out}")

    if col2.button("Reject Permanently"):
        out = verified_dir / "manual_rejected.jsonl"
        existing = read_jsonl(out)
        existing.append({"decision": "reject", "reason": reason, "record": row})
        write_jsonl(out, existing)
        st.warning(f"Rejected into {out}")

    if col3.button("Keep in Queue"):
        st.info("No change.")


if __name__ == "__main__":
    main()
