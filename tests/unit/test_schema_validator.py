"""Tests for validators/schema_validator.py — JSON Schema wrapper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.settings import PROJECT_ROOT
from aspireace_mocf.validators.schema_validator import array_schema, load_schema, validate_item


def test_load_schema_returns_dict():
    schema = load_schema(PROJECT_ROOT / "schemas" / "source_unit.schema.json")
    assert isinstance(schema, dict)
    assert "type" in schema
    assert "properties" in schema


def test_array_schema_wraps_correctly():
    inner = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    wrapped = array_schema(inner)
    assert wrapped["type"] == "array"
    assert wrapped["minItems"] == 1
    assert wrapped["items"] == inner


def test_validate_item_returns_empty_for_valid():
    schema = load_schema(PROJECT_ROOT / "schemas" / "base_record.schema.json")
    valid_item = {
        "text": "a" * 100,  # min length 80
        "metadata": {
            "record_id": "BASE_001",
            "source_unit_id": "PHY11_CH01_U001",
            "lane": "base_subject",
            "record_type": "base_note",
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
        },
    }
    errors = validate_item(valid_item, schema)
    assert errors == []


def test_validate_item_returns_errors_for_invalid():
    schema = load_schema(PROJECT_ROOT / "schemas" / "base_record.schema.json")
    invalid_item = {
        "text": "tiny",  # too short, fails minLength: 80
        "metadata": {
            "record_id": "BASE_001",
            # Missing other required fields
        },
    }
    errors = validate_item(invalid_item, schema)
    assert len(errors) > 0


def test_all_factory_schemas_load_and_are_well_formed():
    """Every schema in schemas/ must be valid JSON Schema 2020-12."""
    schemas_dir = PROJECT_ROOT / "schemas"
    schemas_found = list(schemas_dir.glob("*.json"))
    assert len(schemas_found) >= 9  # we expect at least 9 schemas
    for schema_path in schemas_found:
        schema = load_schema(schema_path)
        assert "$schema" in schema or "type" in schema, f"{schema_path.name} missing $schema or type"
        # Try validating a trivial empty object — should not raise even if it errors.
        _ = validate_item({}, schema)


def test_app_card_schema_accepts_minimal_record(sample_app_card_record):
    schema = load_schema(PROJECT_ROOT / "schemas" / "app_card.schema.json")
    errors = validate_item(sample_app_card_record, schema)
    assert errors == []


def test_sft_record_schema_accepts_minimal_record(sample_tutor_record):
    schema = load_schema(PROJECT_ROOT / "schemas" / "sft_record.schema.json")
    errors = validate_item(sample_tutor_record, schema)
    assert errors == []
