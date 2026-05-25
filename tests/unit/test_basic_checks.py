"""Tests for validators/basic_checks.py — record-shape + bad-phrase + train-allow gate."""
from __future__ import annotations

import pytest

from aspireace_mocf.utils.errors import VerificationErrorCode
from aspireace_mocf.validators.basic_checks import BAD_PHRASES_LOWER, record_errors


class TestTextRecordShape:
    def test_well_formed_text_record_has_no_errors(self, sample_training_record):
        errors = record_errors(sample_training_record)
        assert errors == []

    def test_text_too_short_returns_error(self):
        record = {"text": "short text", "metadata": {"drafted_by": "api_model", "train_allowed": False, "quality_status": "draft"}}
        errors = record_errors(record)
        assert VerificationErrorCode.TEXT_TOO_SHORT in errors


class TestMessagesRecordShape:
    def test_well_formed_messages_record_has_no_errors(self, sample_tutor_record):
        errors = record_errors(sample_tutor_record)
        assert errors == []

    def test_messages_missing_returns_error(self):
        record = {"messages": [], "metadata": {"drafted_by": "api_model"}}
        errors = record_errors(record)
        assert VerificationErrorCode.MESSAGES_MISSING in errors

    def test_messages_not_a_list_returns_error(self):
        record = {"messages": "not a list", "metadata": {}}
        errors = record_errors(record)
        assert VerificationErrorCode.MESSAGES_MISSING in errors

    def test_wrong_role_order_returns_error(self):
        record = {
            "messages": [
                {"role": "assistant", "content": "should not be first"},
                {"role": "user", "content": "should not be second"},
            ],
            "metadata": {"drafted_by": "api_model"},
        }
        errors = record_errors(record)
        assert VerificationErrorCode.BAD_MESSAGE_ROLES in errors

    def test_assistant_too_short_returns_error(self):
        record = {
            "messages": [
                {"role": "user", "content": "Help me with this physics problem please."},
                {"role": "assistant", "content": "Short."},
            ],
            "metadata": {"drafted_by": "api_model"},
        }
        errors = record_errors(record)
        assert VerificationErrorCode.ASSISTANT_TOO_SHORT in errors


class TestAppCardRecordShape:
    def test_well_formed_app_card_has_no_errors(self, sample_app_card_record):
        errors = record_errors(sample_app_card_record)
        assert errors == []


class TestUnknownShape:
    def test_record_with_neither_text_nor_messages_nor_body_errors(self):
        record = {"random_field": "value", "metadata": {}}
        errors = record_errors(record)
        assert VerificationErrorCode.UNKNOWN_RECORD_SHAPE in errors


class TestBadPhraseDetection:
    @pytest.mark.parametrize("bad_phrase", [
        "As an AI, I cannot",
        "Based on the source material provided",
        "I'm sorry, but I cannot generate that.",
        "Your task is to help students.",
        "```json",
        "<|endoftext|>",
    ])
    def test_known_bad_phrase_is_caught(self, bad_phrase):
        # Pad the bad phrase with enough content that text-length doesn't trigger first.
        record = {
            "text": (
                f"{bad_phrase} Dimensional analysis is a powerful technique for "
                f"checking equations in physics. By comparing the dimensions of "
                f"each term, we can detect errors quickly."
            ),
            "metadata": {"drafted_by": "api_model", "train_allowed": False, "quality_status": "draft"},
        }
        errors = record_errors(record)
        assert VerificationErrorCode.BAD_PHRASE_DETECTED in errors

    def test_clean_text_no_bad_phrase(self, sample_training_record):
        errors = record_errors(sample_training_record)
        assert VerificationErrorCode.BAD_PHRASE_DETECTED not in errors

    def test_bad_phrase_library_is_non_empty(self):
        # Defensive: regression-catch if someone accidentally truncates the list.
        assert len(BAD_PHRASES_LOWER) >= 30


class TestTrainAllowabilityGate:
    """This is the legal gate. Test it thoroughly."""

    def test_api_draft_with_train_allowed_true_without_sme_verification_is_rejected(self):
        record = {
            "text": (
                "This text has enough length to pass the length check. " * 5
            ),
            "metadata": {
                "drafted_by": "api_model",
                "train_allowed": True,
                "quality_status": "draft",
            },
        }
        errors = record_errors(record)
        assert VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION in errors

    def test_api_draft_with_train_allowed_true_AND_sme_verified_is_ok(self):
        record = {
            "text": (
                "This text has enough length to pass the length check. " * 5
            ),
            "metadata": {
                "drafted_by": "api_model",
                "train_allowed": True,
                "quality_status": "sme_verified",
            },
        }
        errors = record_errors(record)
        assert VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION not in errors

    def test_human_drafted_with_train_allowed_true_is_ok_regardless_of_status(self):
        record = {
            "text": (
                "This text has enough length to pass the length check. " * 5
            ),
            "metadata": {
                "drafted_by": "teacher_ashwin",
                "train_allowed": True,
                "quality_status": "draft",  # Even draft is fine if not api_model.
            },
        }
        errors = record_errors(record)
        assert VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION not in errors

    def test_api_draft_with_train_allowed_false_is_ok(self):
        record = {
            "text": (
                "This text has enough length to pass the length check. " * 5
            ),
            "metadata": {
                "drafted_by": "api_model",
                "train_allowed": False,
                "quality_status": "draft",
            },
        }
        errors = record_errors(record)
        assert VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION not in errors
