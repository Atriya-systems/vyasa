"""Rubrics loader — per-content-type review rubrics live as JSON files at cms/rubrics/<type>.json.

Why JSON files (not code): rubric content (criteria text, weights, minimum_pass thresholds)
is non-engineering — content leads + senior SMEs should edit them without touching Python.
JSON + a thin loader keeps the editing surface low-friction.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


_RUBRICS_DIR = Path(__file__).resolve().parent / "rubrics"


# Map of factory record_types (lane outputs) → rubric file names. Multiple
# lanes may share a generic 'card' rubric; lanes with specialized concerns
# (questions, formulas, mnemonics) get their own.
RECORD_TYPE_TO_RUBRIC: dict[str, str] = {
    "question": "question",
    "dpp_blueprint": "question",
    "diagnostic_question": "question",
    "pyq_variant": "question",
    "note": "note",
    "notes_card": "note",
    "concept_card": "note",
    "trick": "trick",
    "trick_card": "trick",
    "mnemonic": "mnemonic",
    "mnemonic_card": "mnemonic",
    "formula": "formula",
    "formula_record": "formula",
    "formula_extraction": "formula",
    "misconception_card": "card",
    "grading_rubric": "card",
    "revision_card": "card",
    "career_profile": "career",
    "career_card": "career",
    "parent_copy": "parent_copy",
    "parent_template": "parent_copy",
}


def list_available_rubrics() -> list[str]:
    """Return the list of rubric content_types that have a JSON file present."""
    if not _RUBRICS_DIR.exists():
        return []
    return sorted(p.stem for p in _RUBRICS_DIR.glob("*.json"))


@lru_cache(maxsize=32)
def load_rubric(content_type: str) -> dict[str, Any]:
    """Load the rubric JSON for a content_type. LRU-cached.

    Resolution: look up content_type in RECORD_TYPE_TO_RUBRIC; load that file.
    If content_type not in the map, treat it as a direct filename lookup.
    Falls back to 'card' rubric if nothing matches.

    Raises FileNotFoundError if even the 'card' rubric is missing.
    """
    rubric_name = RECORD_TYPE_TO_RUBRIC.get(content_type, content_type)
    path = _RUBRICS_DIR / f"{rubric_name}.json"
    if not path.exists():
        # Fall back to generic card rubric
        path = _RUBRICS_DIR / "card.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No rubric for content_type {content_type!r} and no fallback 'card.json'. "
                f"Available rubrics: {list_available_rubrics()}"
            )
        _log.warning(
            "rubric_fallback_to_card",
            requested_content_type=content_type,
            fallback="card",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def get_criteria_for_record(content_type: str) -> list[dict[str, Any]]:
    """Convenience: just the criteria list for a record type."""
    rubric = load_rubric(content_type)
    return rubric.get("criteria", [])


def get_minimum_pass_thresholds(content_type: str) -> dict[str, int]:
    """Map of {criterion_key: minimum_pass_score} for the given content_type."""
    criteria = get_criteria_for_record(content_type)
    return {c["key"]: int(c.get("minimum_pass", 3)) for c in criteria}


def clear_rubric_cache() -> None:
    """Reset the LRU cache. Useful in tests when editing rubric files between calls."""
    load_rubric.cache_clear()


def check_scores_against_rubric(
    content_type: str,
    scores: dict[str, int],
) -> tuple[bool, list[str]]:
    """Given scored criteria for a record, return (passes, list_of_failed_keys).

    `passes` is True iff every criterion that has a minimum_pass meets it.
    Criteria not present in scores are treated as missing (failure).
    """
    thresholds = get_minimum_pass_thresholds(content_type)
    failed: list[str] = []
    for key, min_score in thresholds.items():
        actual = scores.get(key)
        if actual is None or actual < min_score:
            failed.append(key)
    return (len(failed) == 0, failed)
