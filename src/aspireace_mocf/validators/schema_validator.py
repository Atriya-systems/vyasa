from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def array_schema(item_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item_schema, "minItems": 1}


def validate_item(item: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return [f"{list(e.path)}: {e.message}" for e in sorted(validator.iter_errors(item), key=lambda e: list(e.path))]
