from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from aspireace_mocf.utils.jsonio import read_jsonl, write_jsonl


def approve_file(input_file: Path, output_file: Path, approver: str, reason: str) -> dict[str, int]:
    rows = read_jsonl(input_file)
    approved = []
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        meta = row.setdefault("metadata", {})
        meta["quality_status"] = "sme_verified"
        meta["train_allowed"] = True
        meta["approved_by"] = approver
        meta["approval_reason"] = reason
        meta["approved_at_utc"] = now
        approved.append(row)
    write_jsonl(output_file, approved)
    return {"approved": len(approved)}
