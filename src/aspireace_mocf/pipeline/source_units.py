from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aspireace_mocf.pipeline.ids import unit_id
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
    prompt = (PROJECT_ROOT / "prompts/01_source_units.md").read_text(encoding="utf-8").format(
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
        raise RuntimeError("source unit generation returned non-array")

    accepted, rejected = [], []
    for serial, row in enumerate(rows, start=1):
        if limit_units and serial > limit_units:
            break
        row["unit_id"] = unit_id(settings.class_level, chapter_no, serial)
        row["source_id"] = source_id
        row["train_allowed"] = False
        errors = validate_item(row, schema)
        if errors:
            rejected.append({"errors": errors, "row": row})
        else:
            accepted.append(row)

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    return {"source_units": len(accepted), "rejected_source_units": len(rejected)}
