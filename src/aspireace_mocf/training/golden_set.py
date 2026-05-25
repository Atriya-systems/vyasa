"""Golden eval set tooling — version + freeze + load senior-teacher-authored eval records.

Purpose: the trained tutor LLM (and prompt-chained baselines) are evaluated
against a fixed, senior-teacher-authored set of query/ideal-response pairs.
This module manages that set:
- Append new records to a working file as teachers author them.
- Freeze the working set into a versioned, hash-pinned release (v1, v2, ...).
- Load a specific version reproducibly for eval runs.

Storage layout:

    eval/golden_sets/
    ├── working/
    │   └── queries.jsonl              appendable; teachers add records here
    ├── v1/
    │   ├── queries.jsonl              frozen at v1 cut, never edited
    │   ├── MANIFEST.json              sha256, count, author IDs, freeze ts
    │   └── CHANGES.md                 narrative notes about this version
    ├── v2/
    │   ├── queries.jsonl
    │   └── MANIFEST.json
    └── ...

Freeze policy: once frozen, a version is never modified. To add records, append
to working/ and freeze a new version when you have enough for an eval pass.

Why versioning matters: if you train tutor_v3 and want to compare its eval
scores to tutor_v2's eval scores, both must be evaluated against the SAME
golden set version, otherwise the comparison is meaningless. Versioning +
hash-pinning makes this enforcible.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.hashing import sha256_file
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl
from aspireace_mocf.utils.logging import get_logger
from aspireace_mocf.validators.schema_validator import load_schema, validate_item


_log = get_logger(__name__)


@dataclass(frozen=True)
class GoldenSetPaths:
    """Resolved paths for a golden-set storage tree."""

    root: Path

    @property
    def working_dir(self) -> Path:
        return self.root / "working"

    @property
    def working_file(self) -> Path:
        return self.working_dir / "queries.jsonl"

    def version_dir(self, version: str) -> Path:
        return self.root / version

    def version_file(self, version: str) -> Path:
        return self.version_dir(version) / "queries.jsonl"

    def version_manifest(self, version: str) -> Path:
        return self.version_dir(version) / "MANIFEST.json"


def _load_record_schema() -> dict[str, Any]:
    """Load the golden-record JSON schema. Cached at module level isn't worth it
    here; the file is tiny and loaded rarely."""
    from aspireace_mocf.settings import PROJECT_ROOT
    return load_schema(PROJECT_ROOT / "schemas" / "tutor_eval_record.schema.json")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def append_record(
    *,
    record: dict[str, Any],
    golden_set_root: Path = Path("eval/golden_sets"),
) -> dict[str, Any]:
    """Append a single golden record to the working file.

    Validates against ``schemas/tutor_eval_record.schema.json`` before writing.
    If the record lacks ``authored_at_utc``, it's set to now.
    Raises ValueError on schema validation failure.
    """
    paths = GoldenSetPaths(root=Path(golden_set_root))
    paths.working_dir.mkdir(parents=True, exist_ok=True)

    record.setdefault("authored_at_utc", _now())

    schema = _load_record_schema()
    errors = validate_item(record, schema)
    if errors:
        raise ValueError(
            f"Golden record failed schema validation. record_id={record.get('record_id')!r} "
            f"errors={errors!r}"
        )

    # Append, don't overwrite.
    with paths.working_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _log.info(
        "golden_record_appended",
        record_id=record.get("record_id"),
        subject=record.get("subject"),
        author_teacher_id=record.get("author_teacher_id"),
        path=str(paths.working_file),
    )
    return record


def list_versions(golden_set_root: Path = Path("eval/golden_sets")) -> list[str]:
    """Return the sorted list of frozen version directories (e.g. ['v1', 'v2'])."""
    root = Path(golden_set_root)
    if not root.exists():
        return []
    versions = []
    for child in root.iterdir():
        if child.is_dir() and child.name not in {"working"} and (child / "MANIFEST.json").exists():
            versions.append(child.name)
    return sorted(versions, key=_version_sort_key)


def _version_sort_key(name: str) -> tuple[int, str]:
    """Sort v1 < v2 < v10. Falls back to lexicographic for non-vN names."""
    if name.startswith("v") and name[1:].isdigit():
        return (int(name[1:]), "")
    return (-1, name)


def next_version(golden_set_root: Path = Path("eval/golden_sets")) -> str:
    """Return the next version name, e.g. 'v3' if v1 + v2 exist."""
    existing = list_versions(golden_set_root)
    n = 0
    for v in existing:
        if v.startswith("v") and v[1:].isdigit():
            n = max(n, int(v[1:]))
    return f"v{n + 1}"


def freeze_version(
    *,
    version: str | None = None,
    golden_set_root: Path = Path("eval/golden_sets"),
    notes: str = "",
) -> dict[str, Any]:
    """Copy the current working file into a frozen versioned directory.

    Generates a MANIFEST.json with sha256, record count, author teacher IDs,
    subject coverage histogram, and freeze timestamp. If ``version`` is None,
    auto-picks the next vN.

    Raises ValueError if working file is empty or missing.
    """
    paths = GoldenSetPaths(root=Path(golden_set_root))
    if not paths.working_file.exists() or paths.working_file.stat().st_size == 0:
        raise ValueError(
            f"Cannot freeze: working file {paths.working_file} is missing or empty. "
            f"Use append_record() to add golden records first."
        )

    if version is None:
        version = next_version(golden_set_root)

    target_dir = paths.version_dir(version)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = paths.version_file(version)

    # Read + revalidate every record before freezing. Defensive: if working/
    # has been hand-edited and contains a bad record, we catch it here.
    records = read_jsonl(paths.working_file)
    schema = _load_record_schema()
    for r in records:
        errors = validate_item(r, schema)
        if errors:
            raise ValueError(
                f"Cannot freeze version {version}: record {r.get('record_id')!r} "
                f"fails schema. errors={errors!r}"
            )

    # Atomic write (rough): write to a temp then rename.
    write_jsonl(target_file, records)

    file_sha = sha256_file(target_file)
    subject_counts: dict[str, int] = {}
    chapter_counts: dict[str, int] = {}
    author_ids: set[str] = set()
    for r in records:
        s = r.get("subject", "_")
        subject_counts[s] = subject_counts.get(s, 0) + 1
        chap_key = f"{s}_CH{r.get('chapter_no', 0):02d}"
        chapter_counts[chap_key] = chapter_counts.get(chap_key, 0) + 1
        if r.get("author_teacher_id"):
            author_ids.add(r["author_teacher_id"])

    manifest = {
        "version": version,
        "frozen_at_utc": _now(),
        "queries_file": str(target_file.relative_to(paths.root)) if paths.root in target_file.parents else str(target_file),
        "sha256": file_sha,
        "record_count": len(records),
        "subject_counts": subject_counts,
        "chapter_counts": chapter_counts,
        "author_teacher_ids": sorted(author_ids),
        "notes": notes,
    }
    write_json(paths.version_manifest(version), manifest)

    # Optional human-readable changes file alongside the manifest.
    changes_path = target_dir / "CHANGES.md"
    changes_path.write_text(
        f"# Golden set {version}\n\n"
        f"Frozen at: {manifest['frozen_at_utc']}\n"
        f"Record count: {manifest['record_count']}\n"
        f"SHA-256: {manifest['sha256']}\n\n"
        f"## Subject coverage\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in sorted(subject_counts.items()))
        + "\n\n## Authors\n\n"
        + "\n".join(f"- {a}" for a in sorted(author_ids))
        + (f"\n\n## Notes\n\n{notes}\n" if notes else "\n"),
        encoding="utf-8",
    )

    _log.info(
        "golden_set_frozen",
        version=version,
        record_count=len(records),
        sha256=file_sha,
        subject_counts=subject_counts,
        author_count=len(author_ids),
    )
    return manifest


def load_version(
    version: str,
    golden_set_root: Path = Path("eval/golden_sets"),
    *,
    verify_hash: bool = True,
) -> list[dict[str, Any]]:
    """Load a frozen version. If ``verify_hash``, recomputes sha256 and asserts
    it matches the manifest. Raises if mismatch (tamper detection).

    Returns the list of golden records.
    """
    paths = GoldenSetPaths(root=Path(golden_set_root))
    queries_file = paths.version_file(version)
    manifest_file = paths.version_manifest(version)

    if not queries_file.exists():
        raise FileNotFoundError(
            f"Golden set version {version!r} not found at {queries_file}. "
            f"Available: {list_versions(golden_set_root)}"
        )

    if verify_hash:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        actual = sha256_file(queries_file)
        expected = manifest.get("sha256")
        if actual != expected:
            raise ValueError(
                f"Golden set {version} hash mismatch! "
                f"expected={expected!r} actual={actual!r}. "
                f"File has been tampered with — eval results from this version "
                f"are not trustworthy. Investigate before proceeding."
            )

    return read_jsonl(queries_file)


def working_count(golden_set_root: Path = Path("eval/golden_sets")) -> int:
    """Number of records currently in the working file (un-frozen)."""
    paths = GoldenSetPaths(root=Path(golden_set_root))
    if not paths.working_file.exists():
        return 0
    return len(read_jsonl(paths.working_file))
