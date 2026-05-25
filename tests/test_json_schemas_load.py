from pathlib import Path
import json


def test_all_schema_files_load():
    for path in Path("schemas").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
