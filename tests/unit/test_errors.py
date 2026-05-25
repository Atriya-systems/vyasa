"""Tests for the error enum taxonomy + route_record() helper."""
from __future__ import annotations

import pytest

from aspireace_mocf.utils.errors import (
    FactoryError,
    LLMError,
    LLMErrorCode,
    PipelineError,
    PipelineErrorCode,
    RightsError,
    RightsErrorCode,
    VerificationError,
    VerificationErrorCode,
    FIX_REQUIRED_ERRORS,
    HUMAN_REVIEW_ERRORS,
    HARD_REJECT_ERRORS,
    route_record,
)


def test_factory_error_str_includes_code():
    err = LLMError(code=LLMErrorCode.PROMPT_TOO_LARGE, message="too big")
    assert "prompt_too_large" in str(err)
    assert "too big" in str(err)


def test_each_error_subclass_inherits_factory_error():
    assert issubclass(LLMError, FactoryError)
    assert issubclass(PipelineError, FactoryError)
    assert issubclass(VerificationError, FactoryError)
    assert issubclass(RightsError, FactoryError)


def test_enum_values_are_stable_strings():
    """The enum values are persisted in audit logs + run reports; they cannot
    change silently or old runs become unparseable."""
    assert LLMErrorCode.PROMPT_TOO_LARGE.value == "prompt_too_large"
    assert PipelineErrorCode.LOCKFILE_HELD_BY_OTHER_RUN.value == "lockfile_held_by_other_run"
    assert VerificationErrorCode.SOURCE_SIMILARITY_WARNING.value == "source_similarity_warning"
    assert RightsErrorCode.LANE_NOT_APPROVED.value == "lane_not_approved"


def test_no_overlap_between_routing_categories():
    """A code can be in only ONE routing bucket — otherwise routing is ambiguous."""
    assert not (FIX_REQUIRED_ERRORS & HUMAN_REVIEW_ERRORS)
    assert not (FIX_REQUIRED_ERRORS & HARD_REJECT_ERRORS)
    assert not (HUMAN_REVIEW_ERRORS & HARD_REJECT_ERRORS)


class TestRouteRecord:
    def test_no_errors_means_accepted(self):
        assert route_record([]) == "accepted"

    def test_hard_reject_wins_over_others(self):
        codes = [
            VerificationErrorCode.SCHEMA_MISMATCH,
            VerificationErrorCode.SOURCE_SIMILARITY_WARNING,
            VerificationErrorCode.JUDGE_ERROR,
        ]
        assert route_record(codes) == "rejected"

    def test_fix_required_wins_over_human_review(self):
        codes = [
            VerificationErrorCode.SOURCE_SIMILARITY_WARNING,
            VerificationErrorCode.JUDGE_ERROR,
        ]
        assert route_record(codes) == "fix_required"

    def test_judge_error_routes_to_human(self):
        assert route_record([VerificationErrorCode.JUDGE_ERROR]) == "human_review"

    def test_only_similarity_routes_to_fix(self):
        assert route_record([VerificationErrorCode.SOURCE_SIMILARITY_WARNING]) == "fix_required"

    def test_only_judge_fix_routes_to_fix(self):
        assert route_record([VerificationErrorCode.JUDGE_FIX_REQUIRED]) == "fix_required"

    def test_judge_reject_is_hard_reject(self):
        assert route_record([VerificationErrorCode.JUDGE_REJECT]) == "rejected"

    def test_bad_phrase_is_hard_reject(self):
        assert route_record([VerificationErrorCode.BAD_PHRASE_DETECTED]) == "rejected"

    def test_api_draft_train_allowed_without_sme_is_hard_reject(self):
        # This is the legal-gate enforcement — must always reject hard.
        assert route_record([VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION]) == "rejected"
