"""M4 additions to prompt_loader tests — style addendum layer.

The base prompt_loader tests live at tests/unit/test_prompt_loader.py and
were written in M1. This file specifically tests the M4 style-addendum
extension.
"""
from __future__ import annotations

import pytest

from aspireace_mocf.pipeline.prompt_loader import (
    ALLOWED_STYLES,
    clear_prompt_cache,
    load_prompt,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_prompt_cache()
    yield
    clear_prompt_cache()


class TestAllowedStyles:
    def test_allowed_styles_match_schema(self):
        # Must mirror the enum in app_card.schema.json
        assert "" in ALLOWED_STYLES
        assert "concise" in ALLOWED_STYLES
        assert "detailed" in ALLOWED_STYLES
        assert "analogy_led" in ALLOWED_STYLES
        assert len(ALLOWED_STYLES) == 4


class TestStyleAddendum:
    def test_no_style_means_no_style_section(self):
        text = load_prompt("01_source_units.md")
        assert "Explanation style" not in text

    def test_concise_style_adds_concise_addendum(self):
        text = load_prompt("01_source_units.md", style="concise")
        assert "Explanation style" in text  # the separator
        assert "CONCISE" in text or "concise" in text.lower()
        assert "60-100 words" in text or "tight" in text.lower()

    def test_detailed_style_adds_detailed_addendum(self):
        text = load_prompt("01_source_units.md", style="detailed")
        assert "DETAILED" in text or "detailed" in text.lower()
        assert "200-400 words" in text or "scaffolding" in text.lower()

    def test_analogy_led_style_adds_analogy_addendum(self):
        text = load_prompt("01_source_units.md", style="analogy_led")
        assert "ANALOGY" in text or "analogy" in text.lower()
        assert "everyday life" in text.lower() or "cricket" in text.lower()

    def test_empty_style_is_treated_as_no_style(self):
        text_empty = load_prompt("01_source_units.md", style="")
        text_none = load_prompt("01_source_units.md", style=None)
        assert text_empty == text_none
        assert "Explanation style" not in text_empty

    def test_unknown_style_is_silently_ignored(self):
        # Style not in ALLOWED_STYLES → no addendum applied, no exception.
        text = load_prompt("01_source_units.md", style="haiku")
        assert "Explanation style" not in text

    def test_case_insensitive_style(self):
        a = load_prompt("01_source_units.md", style="CONCISE")
        b = load_prompt("01_source_units.md", style="concise")
        c = load_prompt("01_source_units.md", style="Concise")
        assert a == b == c


class TestSubjectAndStyleCompose:
    def test_subject_then_style_both_appear(self):
        text = load_prompt("01_source_units.md", subject="Physics", style="concise")
        # Subject addendum section
        assert "Subject-specific guidance" in text
        assert "Physics-specific guidance" in text
        # Style addendum section
        assert "Explanation style" in text
        assert "CONCISE" in text or "concise" in text.lower()

    def test_subject_appears_before_style(self):
        text = load_prompt("01_source_units.md", subject="Chemistry", style="detailed")
        subject_idx = text.find("Subject-specific guidance")
        style_idx = text.find("Explanation style")
        assert subject_idx > 0
        assert style_idx > 0
        assert subject_idx < style_idx  # subject section must come first


class TestStylePromptFilesPresent:
    """Every style key in ALLOWED_STYLES (except empty) must have a file."""

    @pytest.mark.parametrize("style", ["concise", "detailed", "analogy_led"])
    def test_style_addendum_file_loads(self, style):
        # Loading with each allowed style must succeed without raising.
        text = load_prompt("01_source_units.md", style=style)
        assert "Explanation style" in text


class TestCacheIncludesStyleKey:
    """LRU cache must include style in its key — otherwise different styles
    would return the same cached result."""

    def test_different_styles_yield_different_results(self):
        a = load_prompt("01_source_units.md", style="concise")
        b = load_prompt("01_source_units.md", style="detailed")
        assert a != b
