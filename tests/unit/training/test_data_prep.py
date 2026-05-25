"""Tests for training/data_prep.py — the legal gate at training time."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.training.data_prep import (
    DataPrepConfig,
    LaneCounts,
    TRAIN_LANES_TRAINABLE,
    _filter_record,
    _record_is_well_formed,
    _stratify_key,
    discover_approved_jsonl,
    prepare_dataset,
)


# ---------- helpers ----------


def _good_base_record(text="x" * 200, **overrides):
    record = {
        "text": text,
        "metadata": {
            "record_id": "BASE_001",
            "source_unit_id": "PHY11_CH01_U001",
            "source_id": "SME_PHY11_001",
            "lane": "base_subject",
            "record_type": "base_note",
            "subject": "Physics",
            "chapter_no": 1,
            "quality_status": "sme_verified",
            "train_allowed": True,
            "drafted_by": "api_model",
            "approved_by": "teacher_ashwin",
            "approved_at_utc": "2026-05-25T10:00:00+00:00",
        },
    }
    record["metadata"].update(overrides)
    return record


def _good_tutor_record(**overrides):
    record = {
        "messages": [
            {"role": "user", "content": "Help me with dimensional analysis."},
            {"role": "assistant", "content": "Dimensional analysis lets us check the consistency of equations by comparing the dimensions of each term."},
        ],
        "metadata": {
            "record_id": "TUTOR_001",
            "source_unit_id": "PHY11_CH01_U001",
            "source_id": "SME_PHY11_001",
            "lane": "tutor_app",
            "record_type": "doubt_hint_misconception_revision",
            "subject": "Physics",
            "chapter_no": 1,
            "quality_status": "sme_verified",
            "train_allowed": True,
            "drafted_by": "api_model",
            "approved_by": "teacher_ashwin",
            "approved_at_utc": "2026-05-25T10:00:00+00:00",
        },
    }
    record["metadata"].update(overrides)
    return record


def _config(tmp_path: Path, **overrides):
    base = {
        "dataset_id": "test_dataset",
        "target_model_name": "Qwen/Qwen3-8B",
        "max_seq_length": 4096,
        "eval_ratio": 0.2,
        "random_seed": 42,
        "artifacts_root": tmp_path / "artifacts",
    }
    base.update(overrides)
    return DataPrepConfig(**base)


# ---------- the legal gate ----------


class TestLegalGateAtTraining:
    """No record should reach training data unless ALL gates pass."""

    def test_good_record_passes(self):
        passes, reason = _filter_record(_good_base_record(), "base_subject", _config(Path("/tmp")))
        assert passes is True
        assert reason is None

    def test_train_allowed_false_rejected(self):
        record = _good_base_record(train_allowed=False)
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "not_train_allowed"

    def test_train_allowed_missing_rejected(self):
        record = _good_base_record()
        del record["metadata"]["train_allowed"]
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "not_train_allowed"

    def test_not_sme_verified_rejected(self):
        record = _good_base_record(quality_status="draft")
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "not_sme_verified"

    def test_junior_reviewed_rejected_not_sme(self):
        # Junior reviewers can only stage, not finalize. junior_reviewed != sme_verified.
        record = _good_base_record(quality_status="junior_reviewed", train_allowed=False)
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        # train_allowed checked first
        assert reason == "not_train_allowed"

    def test_missing_approver_rejected(self):
        record = _good_base_record(approved_by="")
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "missing_approver"

    def test_missing_approval_timestamp_rejected(self):
        record = _good_base_record(approved_at_utc=None)
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "missing_approval_timestamp"

    def test_invalid_approval_timestamp_rejected(self):
        record = _good_base_record(approved_at_utc="not-a-date")
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "missing_approval_timestamp"

    def test_missing_drafted_by_rejected(self):
        record = _good_base_record(drafted_by="")
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "missing_drafted_by"

    def test_app_card_lane_rejected_not_trainable(self):
        # notes / tricks / etc. are NEVER trainable. Hard gate.
        record = _good_base_record(lane="notes")
        passes, reason = _filter_record(record, "notes", _config(Path("/tmp")))
        assert passes is False
        assert reason == "wrong_lane"


class TestShapeChecks:
    def test_base_record_with_empty_text_rejected(self):
        record = _good_base_record(text="")
        # Actually empty text is caught early via the dataclass field.
        record["text"] = "   "
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp")))
        assert passes is False
        assert reason == "empty_content"

    def test_tutor_record_with_missing_messages_rejected(self):
        record = _good_tutor_record()
        record["messages"] = []
        passes, reason = _filter_record(record, "tutor_app", _config(Path("/tmp")))
        assert passes is False
        assert reason == "schema_mismatch"

    def test_tutor_record_with_empty_assistant_content_rejected(self):
        record = _good_tutor_record()
        record["messages"][1]["content"] = ""
        passes, reason = _filter_record(record, "tutor_app", _config(Path("/tmp")))
        assert passes is False
        assert reason == "empty_content"


class TestTokenBudget:
    def test_record_within_budget_passes(self):
        record = _good_base_record(text="x" * 1000)
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp"), max_seq_length=2048))
        assert passes is True

    def test_record_exceeding_budget_rejected(self):
        # max_seq_length = 100 tokens; text of 10K chars >> 100 tokens
        record = _good_base_record(text="x" * 10000)
        passes, reason = _filter_record(record, "base_subject", _config(Path("/tmp"), max_seq_length=100))
        assert passes is False
        assert reason == "exceeds_max_seq_length"


class TestStratification:
    def test_stratify_key_composes_metadata(self):
        record = _good_base_record(subject="Chemistry", chapter_no=5, record_type="formula")
        key = _stratify_key(record, ("subject", "chapter_no", "record_type"))
        assert key == "Chemistry|5|formula"

    def test_stratify_key_handles_missing_fields(self):
        record = {"metadata": {"subject": "Physics"}}
        key = _stratify_key(record, ("subject", "chapter_no", "record_type"))
        assert key == "Physics|_|_"


# ---------- end-to-end ----------


class TestPrepareDataset:
    def test_end_to_end_with_one_lane(self, tmp_path):
        # 20 base_subject records, stratified across 4 chapter+record_type buckets.
        records = []
        for i in range(20):
            r = _good_base_record(text="x" * 200 + f" record {i}")
            r["metadata"]["chapter_no"] = (i % 2) + 1
            r["metadata"]["record_type"] = "base_note" if i % 2 == 0 else "formula"
            r["metadata"]["record_id"] = f"BASE_{i:03d}"
            records.append(r)

        input_path = tmp_path / "base_subject_sme_verified.jsonl"
        input_path.write_text(
            "\n".join(json.dumps(r) for r in records),
            encoding="utf-8",
        )

        config = _config(tmp_path, eval_ratio=0.2)
        manifest = prepare_dataset(
            sources={"base_subject": [input_path]},
            config=config,
        )

        assert manifest["total_accepted"] == 20
        assert manifest["total_train"] + manifest["total_eval"] == 20
        # Some eval split should exist given stratification + eval_ratio=0.2
        assert manifest["total_eval"] >= 1
        # Files exist
        artefact_dir = Path(manifest["artefact_dir"])
        assert (artefact_dir / "base_subject_train.jsonl").exists()
        assert (artefact_dir / "base_subject_eval.jsonl").exists()
        assert (artefact_dir / "manifest.json").exists()

    def test_rejected_records_go_to_filtered_out(self, tmp_path):
        good = _good_base_record(text="x" * 200)
        bad = _good_base_record(text="x" * 200, train_allowed=False)
        bad["metadata"]["record_id"] = "BAD_001"

        input_path = tmp_path / "input.jsonl"
        input_path.write_text(
            json.dumps(good) + "\n" + json.dumps(bad) + "\n",
            encoding="utf-8",
        )

        config = _config(tmp_path)
        manifest = prepare_dataset(
            sources={"base_subject": [input_path]},
            config=config,
        )

        assert manifest["total_accepted"] == 1
        assert manifest["total_rejected"] == 1
        # Filtered-out file should contain the bad record with reason.
        filtered_path = Path(manifest["artefact_dir"]) / "filtered_out.jsonl"
        assert filtered_path.exists()
        lines = filtered_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["filter_reason"] == "not_train_allowed"
        assert entry["record_id"] == "BAD_001"

    def test_rejects_non_trainable_lane(self, tmp_path):
        config = _config(tmp_path)
        with pytest.raises(ValueError, match="Non-trainable"):
            prepare_dataset(sources={"notes": [tmp_path / "notes.jsonl"]}, config=config)


class TestDiscoverApprovedJsonl:
    def test_discovers_files_in_run_dir(self, tmp_path):
        run_dir = tmp_path / "runs" / "test_run"
        verified = run_dir / "verified"
        verified.mkdir(parents=True)
        (verified / "base_subject_sme_verified.jsonl").write_text("", encoding="utf-8")
        (verified / "tutor_app_sme_verified.jsonl").write_text("", encoding="utf-8")
        (verified / "notes_sme_verified.jsonl").write_text("", encoding="utf-8")  # Not trainable

        result = discover_approved_jsonl([run_dir])
        assert len(result["base_subject"]) == 1
        assert len(result["tutor_app"]) == 1
        assert "notes" not in result  # only trainable lanes returned
        for lane in TRAIN_LANES_TRAINABLE:
            assert lane in result
