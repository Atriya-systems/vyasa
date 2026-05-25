"""Prompt loader — resolves base prompt + optional subject addendum into final text.

Purpose: single entry point for loading any LLM prompt template. Resolves the
prompt path with versioning awareness (prefer `prompts/v1/<file>` over
legacy `prompts/<file>`) and concatenates a per-subject addendum from
`prompts/subjects/<subject>/addendum.md` when present.

See `prompts/README.md` for the full resolution-order + versioning spec.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aspireace_mocf.settings import PROJECT_ROOT
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)

_SUBJECT_SEPARATOR = "\n\n---\n## Subject-specific guidance\n\n"


def _resolve_base_path(filename: str) -> Path:
    """Find the canonical base prompt path. Prefers v1/, falls back to legacy."""
    v1 = PROJECT_ROOT / "prompts" / "v1" / filename
    if v1.exists():
        return v1
    legacy = PROJECT_ROOT / "prompts" / filename
    if legacy.exists():
        _log.warning(
            "prompt_legacy_path_used",
            filename=filename,
            advice="Move file under prompts/v1/ to silence this warning.",
        )
        return legacy
    raise FileNotFoundError(
        f"Prompt template not found: {filename!r} "
        f"(looked in prompts/v1/ and prompts/). "
        f"Check prompts/README.md for the expected layout."
    )


def _subject_addendum_path(subject: str | None) -> Path | None:
    """Return the addendum path if it exists, else None."""
    if not subject:
        return None
    candidate = PROJECT_ROOT / "prompts" / "subjects" / subject.strip().lower() / "addendum.md"
    return candidate if candidate.exists() else None


@lru_cache(maxsize=128)
def load_prompt(filename: str, subject: str | None = None) -> str:
    """Return the final prompt text: base + (optional) subject addendum.

    Args:
        filename: prompt file name, e.g. ``"01_source_units.md"``.
        subject: subject name (case-insensitive), e.g. ``"Chemistry"``.
            When None, no addendum is appended.

    Returns:
        Concatenated prompt text.

    Raises:
        FileNotFoundError: when the base prompt is missing entirely.

    The result is LRU-cached because prompt templates don't change at runtime;
    re-reading them on every LLM call wastes ~0.5 ms × thousands of records.
    """
    base_path = _resolve_base_path(filename)
    base_text = base_path.read_text(encoding="utf-8")
    addendum_path = _subject_addendum_path(subject)
    if addendum_path is None:
        return base_text
    addendum_text = addendum_path.read_text(encoding="utf-8")
    _log.debug(
        "prompt_loaded_with_addendum",
        filename=filename,
        subject=subject,
        base_path=str(base_path),
        addendum_path=str(addendum_path),
    )
    return base_text + _SUBJECT_SEPARATOR + addendum_text


def clear_prompt_cache() -> None:
    """Useful in tests when editing prompts between calls."""
    load_prompt.cache_clear()
