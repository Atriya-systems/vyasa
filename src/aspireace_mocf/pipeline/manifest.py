from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.hashing import sha256_file
from aspireace_mocf.utils.jsonio import write_json


def write_manifest(path: Path, run_id: str, input_file: Path, status: str, outputs: dict[str, str], counts: dict[str, Any], rights_summary: dict[str, Any]) -> dict[str, Any]:
    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_file),
        "input_sha256": sha256_file(input_file) if input_file.exists() else None,
        "status": status,
        "outputs": outputs,
        "counts": counts,
        "rights_summary": rights_summary,
    }
    write_json(path, manifest)
    return manifest
