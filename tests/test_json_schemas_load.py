"""Smoke test — every JSON Schema file in schemas/ parses cleanly.

Kept at top-level for back-compat. Deeper schema validation lives in
tests/unit/test_schema_validator.py.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_all_schema_files_load():
    schemas_dir = Path(__file__).resolve().parent.parent / "schemas"
    schema_files = list(schemas_dir.glob("*.json"))
    assert len(schema_files) >= 9, f"Expected >=9 schemas, found {len(schema_files)}"
    for path in schema_files:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(schema, dict), f"{path.name} did not parse to dict"
        assert "$schema" in schema or "type" in schema, f"{path.name} missing $schema or type"
