from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import PROJECT_ROOT, Settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl
from aspireace_mocf.utils.text import extract_owned_text
from aspireace_mocf.utils.jsonio import read_json
from aspireace_mocf.validators.basic_checks import record_errors
from aspireace_mocf.validators.schema_validator import load_schema, validate_item
from aspireace_mocf.validators.similarity import max_similarity_to_sources


def _schema_for_lane(lane: str) -> str:
    if lane == "base_subject":
        return "base_record.schema.json"
    if lane in {"tutor_app", "content_generator"}:
        return "sft_record.schema.json"
    return "app_card.schema.json"


def _judge(row: dict[str, Any], llm: LLMClient) -> dict[str, Any]:
    schema = load_schema(PROJECT_ROOT / "schemas/judge_response.schema.json")
    template = (PROJECT_ROOT / "prompts/06_judge.md").read_text(encoding="utf-8")
    return llm.chat_json(template.format(record_json=json.dumps(row, ensure_ascii=False, indent=2)), schema=schema, temperature=0.0, max_tokens=2000)


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
    rows = read_jsonl(input_file)
    schema = load_schema(PROJECT_ROOT / f"schemas/{_schema_for_lane(lane)}")
    source_text = extract_owned_text(read_json(source_file))
    accepted, rejected, fix, human = [], [], [], []

    for row in rows:
        errors = validate_item(row, schema)
        if lane in {"base_subject", "tutor_app", "content_generator"}:
            errors += record_errors(row)

        text = row.get("text") or " ".join(m.get("content", "") for m in row.get("messages", [])) or row.get("body", "")
        sim = max_similarity_to_sources(text, [source_text])
        if sim >= settings.similarity_warn_threshold:
            errors.append(f"source_similarity_warning:{sim:.3f}")

        judge = None
        if llm_judge and llm is not None and not errors:
            try:
                judge = _judge(row, llm)
                scores = [judge["subject_correctness"], judge["teaching_quality"], judge["source_grounding"], judge["app_usefulness"]]
                if any(s <= 2 for s in scores):
                    errors.append("judge_reject")
                elif any(s == 3 for s in scores):
                    errors.append("judge_fix_required")
            except Exception as exc:
                errors.append(f"llm_judge_error:{exc}")

        if not errors:
            row.setdefault("metadata", {})["quality_status"] = "auto_checked"
            accepted.append(row)
        elif any("similarity_warning" in e or "judge_fix_required" in e for e in errors):
            fix.append({"errors": errors, "judge": judge, "row": row})
        elif any("judge_error" in e for e in errors):
            human.append({"errors": errors, "judge": judge, "row": row})
        else:
            rejected.append({"errors": errors, "judge": judge, "row": row})

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    write_jsonl(fix_queue_file, fix)
    write_jsonl(human_review_file, human)
    report = {"lane": lane, "input": str(input_file), "accepted": len(accepted), "rejected": len(rejected), "fix_required": len(fix), "human_review": len(human)}
    write_json(report_file, report)
    return report
