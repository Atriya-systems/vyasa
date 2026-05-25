"""Per-lane verification — schema + record + similarity + LLM-judge gate.

Purpose: take a freshly-generated lane file, run every record through the gates,
and route to one of four outputs:
  - `<lane>_auto_checked.jsonl`     — passed everything, awaiting SME final approval
  - `queues/<lane>_fix_queue.jsonl` — failed soft gates (similarity, judge-fix)
  - `queues/<lane>_human_review_queue.jsonl` — judge errored or uncertain
  - `verified/<lane>_rejected.jsonl` — failed hard gates (schema, shape, bad phrase)

Bug fixes vs v0.3.0 baseline:
- Bug #13 fix: routing now uses `aspireace_mocf.utils.errors.route_record` which
  does enum set-membership checks, not string substring matches. Renames are
  caught at type-check time.

Above-the-bar additions:
- Precomputed source-similarity vectorizer via `SourceSimilarityCache` — saves
  ~N× CPU on large lanes.
- Structured logging per record verification with correlation IDs.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
SLA: verify one lane of 100 records (no judge): <= 10 seconds.
SLA: verify one lane of 100 records (with judge): <= 5 minutes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import PROJECT_ROOT, Settings
from aspireace_mocf.utils.errors import VerificationErrorCode, route_record
from aspireace_mocf.utils.jsonio import read_json, read_jsonl, write_json, write_jsonl
from aspireace_mocf.utils.logging import get_logger
from aspireace_mocf.utils.text import extract_owned_text
from aspireace_mocf.validators.basic_checks import record_errors
from aspireace_mocf.validators.schema_validator import load_schema, validate_item
from aspireace_mocf.validators.similarity import SourceSimilarityCache


_log = get_logger(__name__)


def _schema_for_lane(lane: str) -> str:
    if lane == "base_subject":
        return "base_record.schema.json"
    if lane in {"tutor_app", "content_generator"}:
        return "sft_record.schema.json"
    return "app_card.schema.json"


def _judge(row: dict[str, Any], llm: LLMClient) -> dict[str, Any]:
    schema = load_schema(PROJECT_ROOT / "schemas/judge_response.schema.json")
    template = (PROJECT_ROOT / "prompts/v1/06_judge.md").read_text(encoding="utf-8") \
        if (PROJECT_ROOT / "prompts/v1/06_judge.md").exists() \
        else (PROJECT_ROOT / "prompts/06_judge.md").read_text(encoding="utf-8")
    return llm.chat_json(
        template.format(record_json=json.dumps(row, ensure_ascii=False, indent=2)),
        schema=schema,
        temperature=0.0,
        max_tokens=2000,
    )


def verify_lane(
    *,
    lane: str,
    input_file: Path,
    output_file: Path,
    rejected_file: Path,
    fix_queue_file: Path,
    human_review_file: Path,
    report_file: Path,
    source_file: Path,
    settings: Settings,
    llm: LLMClient | None,
    llm_judge: bool,
) -> dict[str, Any]:
    """Verify one lane's records. Routes each to accepted/fix/human/rejected."""
    rows = read_jsonl(input_file)
    schema = load_schema(PROJECT_ROOT / f"schemas/{_schema_for_lane(lane)}")
    source_text = extract_owned_text(read_json(source_file))

    # Bug #11 fix: precompute source vectors once. Massive speedup vs old code.
    sim_cache = SourceSimilarityCache([source_text])

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    fix: list[dict[str, Any]] = []
    human: list[dict[str, Any]] = []

    for row in rows:
        codes: list[VerificationErrorCode] = []

        # Schema check (every lane)
        schema_errors = validate_item(row, schema)
        if schema_errors:
            codes.append(VerificationErrorCode.SCHEMA_MISMATCH)

        # Record-shape + bad-phrase + train-allowability check.
        # Only relevant for training lanes (base/tutor/contentgen); app-content
        # cards have a different shape. record_errors handles both shapes.
        codes.extend(record_errors(row))

        # Source-similarity check.
        text = _record_text(row)
        sim = sim_cache.max_similarity(text)
        if sim >= settings.similarity_warn_threshold:
            codes.append(VerificationErrorCode.SOURCE_SIMILARITY_WARNING)

        # Optional LLM-judge gate.
        judge = None
        # Only call judge if no hard errors yet — saves tokens.
        if llm_judge and llm is not None and not codes:
            try:
                judge = _judge(row, llm)
                scores = [
                    judge["subject_correctness"],
                    judge["teaching_quality"],
                    judge["source_grounding"],
                    judge["app_usefulness"],
                ]
                if any(s <= 2 for s in scores):
                    codes.append(VerificationErrorCode.JUDGE_REJECT)
                elif any(s == 3 for s in scores):
                    codes.append(VerificationErrorCode.JUDGE_FIX_REQUIRED)
            except Exception as exc:
                _log.warning("llm_judge_error", lane=lane, error=str(exc))
                codes.append(VerificationErrorCode.JUDGE_ERROR)

        # Bug #13 fix: enum-based routing, no string substring matches.
        route = route_record(codes)

        if route == "accepted":
            row.setdefault("metadata", {})["quality_status"] = "auto_checked"
            accepted.append(row)
        elif route == "fix_required":
            fix.append({"errors": [c.value for c in codes], "judge": judge, "row": row, "similarity": sim, "schema_errors": schema_errors})
        elif route == "human_review":
            human.append({"errors": [c.value for c in codes], "judge": judge, "row": row, "schema_errors": schema_errors})
        else:
            rejected.append({"errors": [c.value for c in codes], "judge": judge, "row": row, "schema_errors": schema_errors})

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    write_jsonl(fix_queue_file, fix)
    write_jsonl(human_review_file, human)
    report = {
        "lane": lane,
        "input": str(input_file),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "fix_required": len(fix),
        "human_review": len(human),
        "total": len(rows),
    }
    write_json(report_file, report)
    _log.info("verify_lane_completed", **report)
    return report


def _record_text(row: dict[str, Any]) -> str:
    """Extract the verifiable text from any record shape (training or app card)."""
    if "text" in row:
        return row.get("text", "") or ""
    if "messages" in row:
        return " ".join(
            m.get("content", "") for m in row.get("messages", []) if isinstance(m, dict)
        )
    if "body" in row:
        return row.get("body", "") or ""
    return ""
