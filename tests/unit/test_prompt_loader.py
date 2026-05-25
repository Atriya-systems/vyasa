"""Tests for pipeline/prompt_loader.py — base prompt + subject addendum resolution."""
from __future__ import annotations

import pytest

from aspireace_mocf.pipeline.prompt_loader import clear_prompt_cache, load_prompt


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_prompt_cache()
    yield
    clear_prompt_cache()


def test_load_base_prompt_without_subject():
    """No subject → just the base v1 prompt, no addendum."""
    text = load_prompt("01_source_units.md")
    assert "Return valid JSON" in text or "JSON" in text  # base prompt content
    assert "Subject-specific guidance" not in text  # no addendum separator


def test_load_with_physics_subject_appends_physics_addendum():
    text = load_prompt("01_source_units.md", subject="Physics")
    assert "Physics-specific guidance" in text
    assert "Subject-specific guidance" in text  # the separator marker
    # Some signature physics-only content (from addendum.md):
    assert "[LT^-1]" in text or "Newton" in text or "JEE-Advanced" in text


def test_load_with_chemistry_subject_appends_chemistry_addendum():
    text = load_prompt("01_source_units.md", subject="Chemistry")
    assert "Chemistry-specific guidance" in text
    assert "IUPAC" in text or "reaction" in text.lower() or "mechanism" in text.lower()


def test_load_with_biology_subject_appends_biology_addendum():
    text = load_prompt("01_source_units.md", subject="Biology")
    assert "Biology-specific guidance" in text
    assert "NEET" in text


def test_load_with_mathematics_subject_appends_math_addendum():
    text = load_prompt("01_source_units.md", subject="Mathematics")
    assert "Mathematics-specific guidance" in text
    assert "LaTeX" in text or "JEE" in text


def test_load_with_unknown_subject_falls_back_to_base():
    """Unknown subject → no addendum file → just the base prompt."""
    text = load_prompt("01_source_units.md", subject="Astrology")
    assert "Subject-specific guidance" not in text


def test_load_with_subject_case_insensitive():
    text_lower = load_prompt("01_source_units.md", subject="physics")
    text_upper = load_prompt("01_source_units.md", subject="PHYSICS")
    text_mixed = load_prompt("01_source_units.md", subject="Physics")
    assert text_lower == text_upper == text_mixed


def test_load_missing_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt.md")


def test_each_lane_prompt_loads():
    """All 6 base prompts in v1/ must resolve."""
    for filename in [
        "01_source_units.md",
        "02_base_subject.md",
        "03_tutor_app.md",
        "04_content_generator.md",
        "05_app_cards.md",
        "06_judge.md",
    ]:
        text = load_prompt(filename)
        assert text  # non-empty


def test_prompt_caching_works():
    """The LRU cache means the function returns the same string for the same args."""
    a = load_prompt("01_source_units.md", subject="Physics")
    b = load_prompt("01_source_units.md", subject="Physics")
    assert a is b  # cached → same object
