"""Tests for validators/rights_validator.py — per-lane CSV ledger gating."""
from __future__ import annotations

import pytest

from aspireace_mocf.validators.rights_validator import load_rights_ledger, validate_source_for_lane


@pytest.fixture
def ledger(sample_rights_ledger_csv):
    return load_rights_ledger(sample_rights_ledger_csv)


class TestSourceFoundInLedger:
    def test_sme_owned_source_allows_all_lanes(self, ledger):
        ok, reason = validate_source_for_lane(ledger, "TEST_PHY11_001", "base_subject")
        assert ok is True
        assert reason == "ok"

        ok, _ = validate_source_for_lane(ledger, "TEST_PHY11_001", "app_content")
        assert ok is True

        ok, _ = validate_source_for_lane(ledger, "TEST_PHY11_001", "rag")
        assert ok is True

    def test_reference_only_blocks_everything(self, ledger):
        ok, reason = validate_source_for_lane(ledger, "TEST_REF_001", "base_subject")
        assert ok is False
        assert "reference_only" in reason or "commercial" in reason  # both fail; ref_only checked first

        ok, _ = validate_source_for_lane(ledger, "TEST_REF_001", "app_content")
        assert ok is False

    def test_licensed_but_no_training_blocks_training_lanes(self, ledger):
        # TEST_NO_TRAIN_001 has commercial=true, ai_training=false, derivative=true.
        ok, reason = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "base_subject")
        assert ok is False
        assert reason == "ai_training_not_allowed"

        ok, _ = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "tutor_app")
        assert ok is False

        ok, _ = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "content_generator")
        assert ok is False

    def test_licensed_no_training_still_allows_app_content_rag_offline(self, ledger):
        # Same source — non-training categories should pass.
        ok, _ = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "app_content")
        assert ok is True

        ok, _ = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "rag")
        assert ok is True

        ok, _ = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "offline")
        assert ok is True


class TestSourceMissingFromLedger:
    def test_unknown_source_id_returns_false(self, ledger):
        ok, reason = validate_source_for_lane(ledger, "UNKNOWN_SOURCE_999", "app_content")
        assert ok is False
        assert reason == "source_id_missing_from_rights_ledger"


class TestApprovedForFilter:
    def test_lane_not_in_approved_for_returns_false(self, ledger):
        # TEST_NO_TRAIN_001 has approved_for="app_content;rag;offline".
        # Try base_subject (which IS blocked by ai_training_allowed=false anyway).
        ok, reason = validate_source_for_lane(ledger, "TEST_NO_TRAIN_001", "base_subject")
        assert ok is False
        # The ai_training_not_allowed check fires before approved_for check.
        assert reason == "ai_training_not_allowed"


class TestEdgeCases:
    def test_empty_ledger_is_handled(self, tmp_path):
        csv = tmp_path / "empty.csv"
        csv.write_text(
            "source_id,source_type,owner,commercial_use_allowed,ai_training_allowed,"
            "derivative_allowed,reference_only,license_doc,approved_for\n",
            encoding="utf-8",
        )
        ledger = load_rights_ledger(csv)
        assert ledger == {}
        ok, reason = validate_source_for_lane(ledger, "anything", "base_subject")
        assert ok is False
        assert reason == "source_id_missing_from_rights_ledger"

    def test_load_ledger_ignores_extra_columns(self, tmp_path):
        # The real source_ledger.csv has teacher_id + seniority columns added in M1.
        # Verify the loader doesn't choke on them.
        csv = tmp_path / "extra_cols.csv"
        csv.write_text(
            "source_id,source_type,owner,commercial_use_allowed,ai_training_allowed,"
            "derivative_allowed,reference_only,license_doc,approved_for,teacher_id,seniority\n"
            "SME_001,SME_OWNED,Atriya,true,true,true,false,LIC_001.pdf,"
            '"base_subject;app_content",teacher_alice,senior\n',
            encoding="utf-8",
        )
        ledger = load_rights_ledger(csv)
        assert "SME_001" in ledger
        ok, _ = validate_source_for_lane(ledger, "SME_001", "base_subject")
        assert ok is True
