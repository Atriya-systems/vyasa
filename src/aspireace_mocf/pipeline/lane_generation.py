from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from aspireace_mocf.pipeline.ids import record_id, card_id
from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import PROJECT_ROOT, Settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_jsonl
from aspireace_mocf.validators.basic_checks import record_errors
from aspireace_mocf.validators.schema_validator import array_schema, load_schema, validate_item


LANE_PROMPTS = {
    "base_subject": ("02_base_subject.md", "base_record.schema.json", "BASE", "base_subject"),
    "tutor_app": ("03_tutor_app.md", "sft_record.schema.json", "TUTOR", "tutor_app"),
    "content_generator": ("04_content_generator.md", "sft_record.schema.json", "CGEN", "content_generator"),
}

APP_LANES = {
    "notes": ("NOTE", "notes_card", "NOTES_BUILDER"),
    "tricks": ("TRICK", "trick_card", "SHORT_TRICK_GENERATOR"),
    "misconceptions": ("MISCARD", "misconception_card", "MISCONCEPTION_REPAIR"),
    "dpp_tests": ("DPP", "dpp_blueprint", "DPP_GENERATOR"),
    "grading_feedback": ("RUBRIC", "grading_rubric", "HSGE_GRADING_FEEDBACK"),
    "revision": ("REV", "revision_card", "REVISION_ENGINE"),
}


def _normalize_train_record(raw: dict[str, Any], unit: dict[str, Any], lane: str, prefix: str, serial: int) -> dict[str, Any]:
    if lane == "base_subject":
        return {
            "text": raw.get("text", ""),
            "metadata": {
                "record_id": record_id(prefix, unit["unit_id"], serial),
                "source_unit_id": unit["unit_id"],
                "source_id": unit["source_id"],
                "lane": lane,
                "record_type": raw.get("metadata", {}).get("record_type", "base_note"),
                "subject": unit["subject"],
                "class_level": unit["class_level"],
                "chapter_no": unit["chapter_no"],
                "chapter_name": unit["chapter_name"],
                "topic": unit["topic"],
                "subtopic": unit["subtopic"],
                "difficulty": unit["difficulty"],
                "quality_status": "draft",
                "train_allowed": False,
                "drafted_by": "api_model",
            },
        }
    return {
        "messages": raw.get("messages", []),
        "metadata": {
            "record_id": record_id(prefix, unit["unit_id"], serial),
            "source_unit_id": unit["unit_id"],
            "source_id": unit["source_id"],
            "lane": lane,
            "record_type": raw.get("metadata", {}).get("record_type", "draft_record"),
            "subject": unit["subject"],
            "class_level": unit["class_level"],
            "chapter_no": unit["chapter_no"],
            "chapter_name": unit["chapter_name"],
            "topic": unit["topic"],
            "subtopic": unit["subtopic"],
            "difficulty": unit["difficulty"],
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
        },
    }


def generate_training_lane(
    *,
    units_file: Path,
    output_file: Path,
    rejected_file: Path,
    lane: str,
    count: int,
    settings: Settings,
    llm: LLMClient,
) -> dict[str, int]:
    prompt_file, schema_file, prefix, _ = LANE_PROMPTS[lane]
    units = read_jsonl(units_file)
    schema = load_schema(PROJECT_ROOT / f"schemas/{schema_file}")
    template = (PROJECT_ROOT / "prompts" / prompt_file).read_text(encoding="utf-8")
    accepted, rejected = [], []

    for unit in tqdm(units, desc=f"Generate {lane}"):
        prompt = template.format(
            source_unit_json=json.dumps(unit, ensure_ascii=False, indent=2),
            count=count,
            unit_id=unit["unit_id"],
            class_level=unit["class_level"],
            subject=unit["subject"],
            exam_targets=", ".join(unit["exam_targets"]),
        )
        try:
            rows = llm.chat_json(prompt, schema=array_schema(schema), temperature=0.2)
        except Exception as exc:
            rejected.append({"unit_id": unit["unit_id"], "lane": lane, "error": str(exc)})
            continue
        for serial, raw in enumerate(rows if isinstance(rows, list) else [], start=1):
            row = _normalize_train_record(raw, unit, lane, prefix, serial)
            errors = validate_item(row, schema) + record_errors(row)
            if errors:
                rejected.append({"unit_id": unit["unit_id"], "lane": lane, "errors": errors, "row": row})
            else:
                accepted.append(row)

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    return {f"{lane}_accepted": len(accepted), f"{lane}_rejected": len(rejected)}


def generate_app_lane(
    *,
    units_file: Path,
    output_file: Path,
    rejected_file: Path,
    lane: str,
    count: int,
    settings: Settings,
    llm: LLMClient,
) -> dict[str, int]:
    prefix, card_type, surface = APP_LANES[lane]
    units = read_jsonl(units_file)
    schema = load_schema(PROJECT_ROOT / "schemas/app_card.schema.json")
    template = (PROJECT_ROOT / "prompts/05_app_cards.md").read_text(encoding="utf-8")
    accepted, rejected = [], []

    for unit in tqdm(units, desc=f"Generate app lane {lane}"):
        prompt = template.format(
            source_unit_json=json.dumps(unit, ensure_ascii=False, indent=2),
            count=count,
            lane=lane,
            unit_id=unit["unit_id"],
            card_type=card_type,
            surface=surface,
        )
        try:
            rows = llm.chat_json(prompt, schema=array_schema(schema), temperature=0.2)
        except Exception as exc:
            rejected.append({"unit_id": unit["unit_id"], "lane": lane, "error": str(exc)})
            continue
        for serial, raw in enumerate(rows if isinstance(rows, list) else [], start=1):
            raw["card_id"] = card_id(prefix, unit["unit_id"], serial)
            raw["source_unit_id"] = unit["unit_id"]
            raw.setdefault("metadata", {})
            raw["metadata"].update({
                "lane": lane,
                "source_id": unit["source_id"],
                "quality_status": "draft",
                "train_allowed": False,
                "drafted_by": "api_model",
                "subject": unit["subject"],
                "class_level": unit["class_level"],
                "chapter_no": unit["chapter_no"],
                "chapter_name": unit["chapter_name"],
                "topic": unit["topic"],
                "subtopic": unit["subtopic"],
            })
            errors = validate_item(raw, schema)
            if errors:
                rejected.append({"unit_id": unit["unit_id"], "lane": lane, "errors": errors, "row": raw})
            else:
                accepted.append(raw)

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    return {f"{lane}_accepted": len(accepted), f"{lane}_rejected": len(rejected)}
