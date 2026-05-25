"""Tests for training/golden_set.py — versioned eval-set tooling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.training.golden_set import (
    append_record,
    freeze_version,
    list_versions,
    load_version,
    next_version,
    working_count,
)


def _good_record(**overrides):
    record = {
        "record_id": "GOLD_PHY11_CH01_001",
        "query": "What is dimensional analysis used for?",
        "ideal_response": (
            "Dimensional analysis is used to check the consistency of equations in physics. "
            "By comparing the dimensions of each term, we can detect algebraic errors and "
            "derive relations up to a dimensionless constant. It cannot find pure numbers."
        ),
        "subject": "Physics",
        "chapter_no": 1,
        "chapter_name": "Units and Measurements",
        "topic": "Dimensional Analysis",
        "difficulty": "basic",
        "dimensions": {
            "subject_correctness": 5,
            "teaching_quality": 5,
            "source_grounding": 5,
            "app_usefulness": 5,
        },
        "author_teacher_id": "teacher_ashwin",
    }
    record.update(overrides)
    return record


# ---------- append ----------


class TestAppendRecord:
    def test_append_creates_working_file(self, tmp_path):
        root = tmp_path / "golden_sets"
        record = _good_record()
        result = append_record(record=record, golden_set_root=root)

        working = root / "working" / "queries.jsonl"
        assert working.exists()
        lines = working.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        loaded = json.loads(lines[0])
        assert loaded["record_id"] == "GOLD_PHY11_CH01_001"
        assert loaded["authored_at_utc"]  # auto-filled

    def test_append_is_append_not_overwrite(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(record_id="GOLD_001"), golden_set_root=root)
        append_record(record=_good_record(record_id="GOLD_002"), golden_set_root=root)
        assert working_count(root) == 2

    def test_invalid_record_raises_schema_error(self, tmp_path):
        root = tmp_path / "golden_sets"
        bad = _good_record(query="x")  # too short (minLength: 5)
        with pytest.raises(ValueError, match="schema"):
            append_record(record=bad, golden_set_root=root)

    def test_invalid_subject_raises(self, tmp_path):
        root = tmp_path / "golden_sets"
        bad = _good_record(subject="Astrology")
        with pytest.raises(ValueError, match="schema"):
            append_record(record=bad, golden_set_root=root)

    def test_invalid_dimension_score_raises(self, tmp_path):
        root = tmp_path / "golden_sets"
        bad = _good_record(dimensions={
            "subject_correctness": 99,  # > 5, schema violation
            "teaching_quality": 5,
            "source_grounding": 5,
            "app_usefulness": 5,
        })
        with pytest.raises(ValueError, match="schema"):
            append_record(record=bad, golden_set_root=root)


# ---------- list + next versions ----------


class TestListVersions:
    def test_empty_root_returns_empty(self, tmp_path):
        assert list_versions(tmp_path / "golden_sets") == []

    def test_lists_only_dirs_with_manifest(self, tmp_path):
        root = tmp_path / "golden_sets"
        (root / "v1").mkdir(parents=True)
        (root / "v1" / "MANIFEST.json").write_text("{}", encoding="utf-8")
        (root / "v2").mkdir()  # No manifest — should be excluded
        (root / "working").mkdir()  # working/ is special; should be excluded
        result = list_versions(root)
        assert result == ["v1"]

    def test_sorts_numerically_not_lexicographically(self, tmp_path):
        root = tmp_path / "golden_sets"
        for v in ["v1", "v2", "v10", "v3"]:
            (root / v).mkdir(parents=True)
            (root / v / "MANIFEST.json").write_text("{}", encoding="utf-8")
        result = list_versions(root)
        # v10 should come AFTER v2, not after v1.
        assert result == ["v1", "v2", "v3", "v10"]


class TestNextVersion:
    def test_first_version_is_v1(self, tmp_path):
        assert next_version(tmp_path / "golden_sets") == "v1"

    def test_increments_from_max(self, tmp_path):
        root = tmp_path / "golden_sets"
        for v in ["v1", "v2"]:
            (root / v).mkdir(parents=True)
            (root / v / "MANIFEST.json").write_text("{}", encoding="utf-8")
        assert next_version(root) == "v3"


# ---------- freeze ----------


class TestFreezeVersion:
    def test_freeze_empty_working_raises(self, tmp_path):
        root = tmp_path / "golden_sets"
        with pytest.raises(ValueError, match="empty"):
            freeze_version(golden_set_root=root)

    def test_freeze_creates_versioned_files(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(record_id="G_001"), golden_set_root=root)
        append_record(record=_good_record(record_id="G_002", subject="Chemistry"), golden_set_root=root)
        manifest = freeze_version(golden_set_root=root, notes="initial freeze")

        version_dir = root / manifest["version"]
        assert (version_dir / "queries.jsonl").exists()
        assert (version_dir / "MANIFEST.json").exists()
        assert (version_dir / "CHANGES.md").exists()
        assert manifest["record_count"] == 2
        assert manifest["sha256"]  # non-empty
        assert manifest["subject_counts"] == {"Physics": 1, "Chemistry": 1}
        assert manifest["author_teacher_ids"] == ["teacher_ashwin"]

    def test_freeze_auto_picks_next_version(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(), golden_set_root=root)
        m1 = freeze_version(golden_set_root=root)
        assert m1["version"] == "v1"

        # Add more, freeze again
        append_record(record=_good_record(record_id="G_002"), golden_set_root=root)
        m2 = freeze_version(golden_set_root=root)
        assert m2["version"] == "v2"

    def test_freeze_explicit_version(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(), golden_set_root=root)
        manifest = freeze_version(version="v42", golden_set_root=root)
        assert manifest["version"] == "v42"


# ---------- load ----------


class TestLoadVersion:
    def test_load_returns_records(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(record_id="G_001"), golden_set_root=root)
        append_record(record=_good_record(record_id="G_002"), golden_set_root=root)
        freeze_version(golden_set_root=root)

        records = load_version("v1", golden_set_root=root)
        assert len(records) == 2

    def test_load_missing_version_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="v99"):
            load_version("v99", golden_set_root=tmp_path / "golden_sets")

    def test_load_detects_tampering(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(), golden_set_root=root)
        freeze_version(golden_set_root=root)

        # Tamper with the queries file after freezing.
        queries_file = root / "v1" / "queries.jsonl"
        queries_file.write_text(
            queries_file.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="hash mismatch"):
            load_version("v1", golden_set_root=root)

    def test_load_skip_hash_check(self, tmp_path):
        root = tmp_path / "golden_sets"
        append_record(record=_good_record(), golden_set_root=root)
        freeze_version(golden_set_root=root)
        # Tamper
        queries_file = root / "v1" / "queries.jsonl"
        queries_file.write_text(queries_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        # Should load anyway when verify_hash=False.
        records = load_version("v1", golden_set_root=root, verify_hash=False)
        assert len(records) >= 1


# ---------- working_count ----------


class TestWorkingCount:
    def test_empty_returns_zero(self, tmp_path):
        assert working_count(tmp_path / "golden_sets") == 0

    def test_counts_appended(self, tmp_path):
        root = tmp_path / "golden_sets"
        for i in range(5):
            append_record(record=_good_record(record_id=f"G_{i:03d}"), golden_set_root=root)
        assert working_count(root) == 5
