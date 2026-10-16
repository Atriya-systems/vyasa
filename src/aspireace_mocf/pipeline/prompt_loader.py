"""Prompt loader — resolves base prompt + optional subject addendum + optional style addendum.

Purpose: single entry point for loading any LLM prompt template. Composes:
  1. base v1 prompt (or legacy fallback)
  2. + subject addendum (Physics / Chemistry / Biology / Mathematics — optional)
  3. + style addendum (concise / detailed / analogy_led — M4 addition, optional)

See `prompts/README.md` for the full resolution-order + versioning spec.

Owner: ATRIYA / Vyasa
Version: 1.1.0 (M4 — adds style-addendum layer)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aspireace_mocf.settings import PROJECT_ROOT
from aspireace_mocf.utils.logging import get_logger

_log = get_logger(__name__)

_SUBJECT_SEPARATOR = "\n\n---\n## Subject-specific guidance\n\n"
_STYLE_SEPARATOR = "\n\n---\n## Explanation style\n\n"


# M4 — allowed styles. Empty string means "no style override (canonical version)."
ALLOWED_STYLES: frozenset[str] = frozenset({"", "concise", "detailed", "analogy_led"})


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
    """Return the subject addendum path if it exists, else None."""
    if not subject:
        return None
    candidate = PROJECT_ROOT / "prompts" / "subjects" / subject.strip().lower() / "addendum.md"
    return candidate if candidate.exists() else None


def _style_addendum_path(style: str | None) -> Path | None:
    """Return the style addendum path if it exists and style is allowed, else None."""
    if not style:
        return None
    key = style.strip().lower()
    if key not in ALLOWED_STYLES or key == "":
        return None
    candidate = PROJECT_ROOT / "prompts" / "styles" / f"{key}.md"
    return candidate if candidate.exists() else None


@lru_cache(maxsize=256)
def load_prompt(filename: str, subject: str | None = None, style: str | None = None) -> str:
    """Return the final prompt text: base + (optional) subject + (optional) style.

    Args:
        filename: prompt file name, e.g. ``"01_source_units.md"``.
        subject: subject name (case-insensitive), e.g. ``"Chemistry"``.
            When None or empty, no subject addendum is appended.
        style: explanation style (case-insensitive), one of
            ``"concise"``, ``"detailed"``, ``"analogy_led"``, or empty/None
            for the canonical version with no style override.

    Returns:
        Concatenated prompt text.

    Raises:
        FileNotFoundError: when the base prompt is missing entirely.

    The result is LRU-cached because prompt templates don't change at runtime;
    re-reading them on every LLM call wastes ~0.5 ms x thousands of records.
    """
    base_path = _resolve_base_path(filename)
    text = base_path.read_text(encoding="utf-8")

    subject_path = _subject_addendum_path(subject)
    if subject_path is not None:
        text += _SUBJECT_SEPARATOR + subject_path.read_text(encoding="utf-8")

    style_path = _style_addendum_path(style)
    if style_path is not None:
        text += _STYLE_SEPARATOR + style_path.read_text(encoding="utf-8")

    _log.debug(
        "prompt_loaded",
        filename=filename,
        subject=subject,
        style=style,
        has_subject_addendum=subject_path is not None,
        has_style_addendum=style_path is not None,
    )
    return text


def clear_prompt_cache() -> None:
    """Useful in tests when editing prompts between calls."""
    load_prompt.cache_clear()
