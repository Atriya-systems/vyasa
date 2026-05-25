from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aspireace_mocf.pipeline.ids import unit_id
from aspireace_mocf.pipeline.prompt_loader import load_prompt
from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import PROJECT_ROOT, Settings
from aspireace_mocf.utils.jsonio import read_json, write_jsonl
from aspireace_mocf.utils.text import extract_owned_text, extract_source_id
from aspireace_mocf.validators.schema_validator import load_schema, array_schema, validate_item


def build_source_units(
    *,
    input_file: Path,
    output_file: Path,
    rejected_file: Path,
    chapter_no: int,
    chapter_name: str,
    settings: Settings,
    llm: LLMClient,
    limit_units: int = 0,
) -> dict[str, int]:
    data = read_json(input_file)
    text = extract_owned_text(data)
    source_id = extract_source_id(data)

    schema = load_schema(PROJECT_ROOT / "schemas/source_unit.schema.json")
    # Subject-aware prompt: base v1 + subject addendum (chem/bio/math/physics).
    prompt_template = load_prompt("01_source_units.md", subject=settings.subject)
    prompt = prompt_template.format(
        source_text=text,
        subject=settings.subject,
        class_level=settings.class_level,
        chapter_no=chapter_no,
        chapter_name=chapter_name,
        source_id=source_id,
        source_type=settings.source_type,
        exam_targets_json=json.dumps(settings.exam_targets, ensure_ascii=False),
    )
    rows = llm.chat_json(prompt, schema=array_schema(schema))
    if not isinstance(rows, list):
        raise RuntimeError(
            f"source unit generation returned {type(rows).__name__}, expected list. "
            f"Check prompts/01_source_units.md — must instruct LLM to return JSON array."
        )

    # Bug #3 fix: validate ALL rows first, then apply limit_units cleanly. The old
    # behaviour broke mid-loop, producing inconsistent partial accepted+rejected
    # lists when limit_units < len(rows). New behaviour validates everything for
    # auditability, then slices accepted (and counts the truncation) so rejected
    # always reflects real validation failures, never artificial cutoffs.
    accepted_all, rejected_all = [], []
    for serial, row in enumerate(rows, start=1):
        row["unit_id"] = unit_id(settings.class_level, chapter_no, serial)
        row["source_id"] = source_id
        row["train_allowed"] = False
        errors = validate_item(row, schema)
        if errors:
            rejected_all.append({"errors": errors, "row": row})
        else:
            accepted_all.append(row)

    if limit_units and len(accepted_all) > limit_units:
        truncated = len(accepted_all) - limit_units
        accepted = accepted_all[:limit_units]
    else:
        truncated = 0
        accepted = accepted_all

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected_all)
    return {
        "source_units": len(accepted),
        "rejected_source_units": len(rejected_all),
        "truncated_by_limit": truncated,
        "total_generated": len(rows),
    }
