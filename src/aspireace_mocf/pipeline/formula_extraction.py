"""Formula extraction — produces structured formula_record entries from source units.

Purpose: notes + tricks lanes already generate free-text content that *references*
formulas. This module produces the STRUCTURED formula library entries the
canonical inventory §A5 asks for: LaTeX expression + plain-English statement +
variable meanings + applicability conditions + worked example + dimensional
consistency check + derivation cross-reference.

Outputs to ``runs/<run_id>/lanes/formulas.jsonl`` alongside the standard lane
outputs. Validates against ``schemas/formula_record.schema.json``.

Called from ``pipeline.runner`` after the notes lane completes, gated by
``settings.extract_formulas``.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
SLA: extract formulas from 5 source units (~15 formula records) in <= 3 minutes
on Qwen3-8B Q4_K_M.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from aspireace_mocf.pipeline.ids import card_id
from aspireace_mocf.pipeline.prompt_loader import load_prompt
from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import PROJECT_ROOT, Settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_jsonl
from aspireace_mocf.utils.logging import get_logger
from aspireace_mocf.validators.schema_validator import array_schema, load_schema, validate_item

_log = get_logger(__name__)


def extract_formulas(
    *,
    units_file: Path,
    output_file: Path,
    rejected_file: Path,
    settings: Settings,
    llm: LLMClient,
) -> dict[str, int]:
    """Walk source units; for each unit that declares formulas, ask the LLM to
    convert them to structured formula records. Writes accepted records to
    ``output_file``; rejected (schema-failed, parse-failed, or empty) go to
    ``rejected_file``.
    """
    units = read_jsonl(units_file)
    schema = load_schema(PROJECT_ROOT / "schemas" / "formula_record.schema.json")
    template = load_prompt("07_formula_extraction.md", subject=settings.subject)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for unit in tqdm(units, desc="Extract formulas"):
        if not unit.get("formulas"):
            # No formulas in this unit; nothing to extract.
            continue

        prompt = template.format(
            source_unit_json=json.dumps(unit, ensure_ascii=False, indent=2),
            count=settings.formula_records_per_unit,
            unit_id=unit["unit_id"],
            subject=unit.get("subject", settings.subject),
            chapter_no=unit.get("chapter_no", 0),
            exam_targets_json=json.dumps(unit.get("exam_targets", settings.exam_targets), ensure_ascii=False),
        )

        try:
            rows = llm.chat_json(
                prompt,
                schema=array_schema(schema),
                temperature=0.1,
                correlation_id=f"formulas:{unit['unit_id']}",
            )
        except Exception as exc:
            _log.warning("formula_extraction_llm_error", unit_id=unit["unit_id"], error=str(exc))
            rejected.append({"unit_id": unit["unit_id"], "error": str(exc)})
            continue

        if not isinstance(rows, list):
            _log.warning("formula_extraction_non_array", unit_id=unit["unit_id"], type=type(rows).__name__)
            rejected.append({"unit_id": unit["unit_id"], "error": "non_array_response"})
            continue

        for serial, raw in enumerate(rows, start=1):
            raw["formula_id"] = card_id("FORMULA", unit["unit_id"], serial)
            raw["source_unit_id"] = unit["unit_id"]
            raw.setdefault("metadata", {})
            raw["metadata"].update({
                "lane": "formulas",
                "source_id": unit.get("source_id"),
                "quality_status": "draft",
                "train_allowed": False,
                "drafted_by": "api_model",
                "record_type": "formula_extraction",
            })
            # Force schema-required fields if LLM omitted them
            raw.setdefault("subject", unit.get("subject", settings.subject))
            raw.setdefault("chapter_no", unit.get("chapter_no", 0))

            schema_errs = validate_item(raw, schema)
            if schema_errs:
                rejected.append({
                    "unit_id": unit["unit_id"],
                    "schema_errors": schema_errs,
                    "row": raw,
                })
            else:
                accepted.append(raw)

    write_jsonl(output_file, accepted)
    write_jsonl(rejected_file, rejected)
    _log.info(
        "formula_extraction_completed",
        accepted=len(accepted),
        rejected=len(rejected),
        units_scanned=len(units),
        units_with_formulas=sum(1 for u in units if u.get("formulas")),
    )
    return {
        "formulas_accepted": len(accepted),
        "formulas_rejected": len(rejected),
        "units_with_formulas": sum(1 for u in units if u.get("formulas")),
    }
