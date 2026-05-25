"""Tests for the M4 formula_record.schema.json — the structured formula library schema."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.settings import PROJECT_ROOT
from aspireace_mocf.validators.schema_validator import load_schema, validate_item


@pytest.fixture
def schema():
    return load_schema(PROJECT_ROOT / "schemas" / "formula_record.schema.json")


def _good_formula(**overrides):
    record = {
        "formula_id": "FORMULA_PHY11_CH03_001",
        "source_unit_id": "PHY11_CH03_U001",
        "latex_expression": "v^2 = u^2 + 2as",
        "statement": "Final velocity squared equals initial velocity squared plus twice the product of acceleration and displacement.",
        "variables": [
            {"symbol": "v", "meaning": "final velocity", "unit": "m/s"},
            {"symbol": "u", "meaning": "initial velocity", "unit": "m/s"},
            {"symbol": "a", "meaning": "acceleration", "unit": "m/s^2"},
            {"symbol": "s", "meaning": "displacement", "unit": "m"},
        ],
        "applicability_conditions": [
            "Motion along a straight line",
            "Constant acceleration",
        ],
        "worked_example": "Car starts at 5 m/s, a=2 m/s^2, s=100 m. v = sqrt(25+400) ≈ 20.6 m/s.",
        "dimensional_check": "[LT^-1]^2 = [LT^-1]^2 + [LT^-2][L] = [L^2 T^-2]. Consistent.",
        "derivation_chapter_ref": "Class 11 Physics, Chapter 3",
        "applied_in_chapters": ["Class 11 Physics Ch4", "Class 11 Physics Ch7"],
        "subject": "Physics",
        "chapter_no": 3,
        "exam_targets": ["JEE", "NEET"],
        "priority": "must_know",
        "metadata": {
            "lane": "formulas",
            "record_type": "formula_extraction",
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
        },
    }
    record.update(overrides)
    return record


class TestFormulaSchemaShape:
    def test_well_formed_record_validates(self, schema):
        errors = validate_item(_good_formula(), schema)
        assert errors == []

    def test_missing_required_field_rejected(self, schema):
        bad = _good_formula()
        del bad["latex_expression"]
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_too_short_statement_rejected(self, schema):
        bad = _good_formula(statement="too short")  # below minLength: 20
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_invalid_subject_enum_rejected(self, schema):
        bad = _good_formula(subject="Astrology")
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_invalid_priority_enum_rejected(self, schema):
        bad = _good_formula(priority="essential")
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_invalid_exam_target_rejected(self, schema):
        bad = _good_formula(exam_targets=["JEE", "GATE"])
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_empty_applicability_conditions_rejected(self, schema):
        bad = _good_formula(applicability_conditions=[])
        errors = validate_item(bad, schema)
        assert len(errors) > 0


class TestFormulaMetadataGate:
    def test_metadata_requires_train_allow_fields(self, schema):
        bad = _good_formula()
        bad["metadata"] = {"lane": "formulas"}  # missing required metadata fields
        errors = validate_item(bad, schema)
        assert len(errors) > 0

    def test_optional_fields_can_be_omitted(self, schema):
        record = _good_formula()
        del record["variables"]
        del record["worked_example"]
        del record["dimensional_check"]
        del record["derivation_chapter_ref"]
        del record["applied_in_chapters"]
        del record["exam_targets"]
        del record["priority"]
        errors = validate_item(record, schema)
        assert errors == []


class TestAppCardSchemaM4Additions:
    """Verify M4 added diagram_url + explanation_style as optional fields without
    breaking existing app card validation."""

    def test_card_without_m4_fields_still_validates(self):
        app_schema = load_schema(PROJECT_ROOT / "schemas" / "app_card.schema.json")
        card = {
            "card_id": "NOTE_001",
            "source_unit_id": "PHY11_CH01_U001",
            "card_type": "notes_card",
            "surface": "NOTES_BUILDER",
            "title": "Dimensional analysis",
            "body": "Dimensional analysis lets us check the consistency of equations.",
            "metadata": {},
        }
        errors = validate_item(card, app_schema)
        assert errors == []

    def test_card_with_diagram_url_validates(self):
        app_schema = load_schema(PROJECT_ROOT / "schemas" / "app_card.schema.json")
        card = {
            "card_id": "NOTE_002",
            "source_unit_id": "BIO11_CH08_U001",
            "card_type": "notes_card",
            "surface": "NOTES_BUILDER",
            "title": "Cell membrane",
            "body": "The fluid mosaic model of the cell membrane.",
            "diagram_url": "content/diagrams/bio/cell_membrane.svg",
            "diagram_caption": "Phospholipid bilayer with embedded proteins (Singer-Nicolson model).",
            "metadata": {},
        }
        errors = validate_item(card, app_schema)
        assert errors == []

    def test_card_with_valid_explanation_style_validates(self):
        app_schema = load_schema(PROJECT_ROOT / "schemas" / "app_card.schema.json")
        card = {
            "card_id": "NOTE_003",
            "source_unit_id": "PHY11_CH01_U001",
            "card_type": "notes_card",
            "surface": "NOTES_BUILDER",
            "title": "Dimensional analysis",
            "body": "Quick check tool for equations.",
            "explanation_style": "concise",
            "metadata": {},
        }
        errors = validate_item(card, app_schema)
        assert errors == []

    def test_card_with_invalid_explanation_style_rejected(self):
        app_schema = load_schema(PROJECT_ROOT / "schemas" / "app_card.schema.json")
        card = {
            "card_id": "NOTE_004",
            "source_unit_id": "PHY11_CH01_U001",
            "card_type": "notes_card",
            "surface": "NOTES_BUILDER",
            "title": "T",
            "body": "B",
            "explanation_style": "haiku",  # not in enum
            "metadata": {},
        }
        errors = validate_item(card, app_schema)
        assert len(errors) > 0
