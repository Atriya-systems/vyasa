from __future__ import annotations

from pathlib import Path
from typing import Any

from aspireace_mocf.pipeline.ids import chunk_id
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl


def build_rag_chunks(units_file: Path, output_file: Path) -> dict[str, int]:
    units = read_jsonl(units_file)
    chunks = []
    for idx, unit in enumerate(units, start=1):
        text = " ".join(unit.get("coverage_points", []))
        if unit.get("formulas"):
            text += " Formulas: " + "; ".join(unit["formulas"])
        if unit.get("common_errors"):
            text += " Common errors: " + "; ".join(unit["common_errors"])
        chunks.append({
            "chunk_id": chunk_id(unit["unit_id"], 1),
            "source_unit_id": unit["unit_id"],
            "text": text.strip(),
            "metadata": {
                "subject": unit["subject"],
                "class_level": unit["class_level"],
                "chapter_no": unit["chapter_no"],
                "chapter_name": unit["chapter_name"],
                "topic": unit["topic"],
                "subtopic": unit["subtopic"],
                "allowed_for_rag": True,
                "allowed_for_training": bool(unit.get("train_allowed", False)),
            },
        })
    write_jsonl(output_file, chunks)
    return {"rag_chunks": len(chunks)}


def build_offline_bundle(units_file: Path, app_card_files: list[Path], output_file: Path, chapter_name: str) -> dict[str, int]:
    units = read_jsonl(units_file)
    items: list[dict[str, Any]] = []
    for file in app_card_files:
        items.extend(read_jsonl(file))
    bundle = {
        "bundle_id": f"OFFLINE_{chapter_name.replace(' ', '_').upper()}",
        "chapter_name": chapter_name,
        "items": items,
        "manifest": {
            "unit_count": len(units),
            "item_count": len(items),
            "offline_allowed": True,
            "cache_strategy": "chapter-level-json",
        },
    }
    write_json(output_file, bundle)
    return {"offline_items": len(items), "offline_units": len(units)}
