"""Tests for utils/text.py — source text extraction + normalization."""
from __future__ import annotations

from aspireace_mocf.utils.text import extract_owned_text, extract_source_id, normalize_text


def test_normalize_text_collapses_whitespace():
    assert normalize_text("hello   world\n\nfoo") == "hello world foo"


def test_normalize_text_dehyphenates_line_breaks():
    """Hyphenated line breaks (PDF artifact) should be joined."""
    assert normalize_text("disper-\nsion") == "dispersion"


def test_normalize_text_fixes_physics_formulas():
    assert "[LT^-1]" in normalize_text("LT-1")
    assert "[MLT^-2]" in normalize_text("MLT-2")


def test_normalize_text_strips_non_breaking_spaces():
    assert "  " not in normalize_text("a b")
    assert normalize_text("a b") == "a b"


def test_extract_source_id_from_dict():
    assert extract_source_id({"source_id": "ABC_001"}) == "ABC_001"


def test_extract_source_id_missing_returns_unknown():
    assert extract_source_id({"other_field": "value"}) == "UNKNOWN_SOURCE"


def test_extract_source_id_handles_non_dict():
    assert extract_source_id(["a", "b"]) == "UNKNOWN_SOURCE"
    assert extract_source_id("string") == "UNKNOWN_SOURCE"


def test_extract_owned_text_prefers_owned_sme_text():
    data = {"owned_sme_text": "the SME source", "text": "alternative"}
    assert extract_owned_text(data) == "the SME source"


def test_extract_owned_text_falls_back_to_text():
    data = {"text": "alternative source"}
    assert extract_owned_text(data) == "alternative source"


def test_extract_owned_text_from_pages():
    data = {"pages": [{"text": "page one"}, {"text": "page two"}]}
    text = extract_owned_text(data)
    assert "page one" in text
    assert "page two" in text


def test_extract_owned_text_from_list():
    data = [{"text": "item one"}, "raw string"]
    text = extract_owned_text(data)
    assert "item one" in text or "raw string" in text


def test_extract_owned_text_handles_dict_with_only_string_values():
    data = {"a": "first", "b": "second", "c": 42}
    text = extract_owned_text(data)
    assert "first" in text and "second" in text
