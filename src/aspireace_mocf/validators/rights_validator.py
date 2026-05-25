from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_rights_ledger(path: Path) -> dict[str, dict[str, Any]]:
    ledger: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_id = row["source_id"].strip()
            ledger[source_id] = {
                "source_id": source_id,
                "source_type": row["source_type"].strip(),
                "owner": row["owner"].strip(),
                "commercial_use_allowed": _bool(row["commercial_use_allowed"]),
                "ai_training_allowed": _bool(row["ai_training_allowed"]),
                "derivative_allowed": _bool(row["derivative_allowed"]),
                "reference_only": _bool(row["reference_only"]),
                "license_doc": row.get("license_doc", "").strip(),
                "approved_for": [x.strip() for x in row.get("approved_for", "").split(";") if x.strip()],
            }
    return ledger


def validate_source_for_lane(ledger: dict[str, dict[str, Any]], source_id: str, lane: str) -> tuple[bool, str]:
    if source_id not in ledger:
        return False, "source_id_missing_from_rights_ledger"
    row = ledger[source_id]
    if row["reference_only"]:
        return False, "source_is_reference_only"
    if not row["commercial_use_allowed"]:
        return False, "commercial_use_not_allowed"
    if lane in {"base_subject", "tutor_app", "content_generator"} and not row["ai_training_allowed"]:
        return False, "ai_training_not_allowed"
    if not row["derivative_allowed"]:
        return False, "derivative_use_not_allowed"
    if row["approved_for"] and lane not in row["approved_for"]:
        return False, f"lane_not_approved:{lane}"
    return True, "ok"
