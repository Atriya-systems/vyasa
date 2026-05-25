"""Error taxonomy — enum-based, never string-matched.

Purpose: every recoverable / observable error path in the factory routes through
one of these enums. Lets verifiers, supervisors, and audit logs check for
specific failure modes without fragile string matching.

Bug fixes vs v0.3.0 baseline:
- Bug #13 fix: replaces string-substring routing like
  `if "similarity_warning" in e or "judge_fix_required" in e` with explicit enum
  comparison. Rename-safe.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

from enum import Enum


class LLMErrorCode(str, Enum):
    """LLM-layer errors (config + provider + response)."""

    CONFIG_MISSING_KEY = "config_missing_key"
    CONFIG_UNKNOWN_PROVIDER = "config_unknown_provider"
    PROMPT_TOO_LARGE = "prompt_too_large"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_CONNECTION = "provider_connection"
    PROVIDER_API_ERROR = "provider_api_error"
    RESPONSE_INVALID_JSON = "response_invalid_json"
    RESPONSE_SCHEMA_MISMATCH = "response_schema_mismatch"


class PipelineErrorCode(str, Enum):
    """Pipeline-orchestration errors."""

    RIGHTS_LEDGER_BLOCKS_ALL_LANES = "rights_ledger_blocks_all_lanes"
    LOCKFILE_HELD_BY_OTHER_RUN = "lockfile_held_by_other_run"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    SOURCE_UNIT_GENERATION_RETURNED_NON_LIST = "source_unit_generation_returned_non_list"
    SUPERVISOR_RETRY_EXHAUSTED = "supervisor_retry_exhausted"


class VerificationErrorCode(str, Enum):
    """Per-record verification errors. Used in `validators/basic_checks.py` +
    `pipeline/verify.py` instead of string substrings.
    """

    SCHEMA_MISMATCH = "schema_mismatch"
    TEXT_TOO_SHORT = "text_too_short"
    BAD_PHRASE_DETECTED = "bad_phrase_detected"
    MESSAGES_MISSING = "messages_missing"
    BAD_MESSAGE_ROLES = "bad_message_roles"
    ASSISTANT_TOO_SHORT = "assistant_too_short"
    UNKNOWN_RECORD_SHAPE = "unknown_record_shape"
    API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION = "api_draft_train_allowed_without_sme_verification"
    SOURCE_SIMILARITY_WARNING = "source_similarity_warning"
    LATEX_INVALID = "latex_invalid"
    JUDGE_FIX_REQUIRED = "judge_fix_required"
    JUDGE_REJECT = "judge_reject"
    JUDGE_ERROR = "judge_error"


class RightsErrorCode(str, Enum):
    """Rights-validator errors."""

    SOURCE_ID_MISSING_FROM_LEDGER = "source_id_missing_from_rights_ledger"
    SOURCE_IS_REFERENCE_ONLY = "source_is_reference_only"
    COMMERCIAL_USE_NOT_ALLOWED = "commercial_use_not_allowed"
    AI_TRAINING_NOT_ALLOWED = "ai_training_not_allowed"
    DERIVATIVE_USE_NOT_ALLOWED = "derivative_use_not_allowed"
    LANE_NOT_APPROVED = "lane_not_approved"


# ----- Exception classes -----


class FactoryError(Exception):
    """Base class for all factory-internal errors."""

    def __init__(self, code: Enum, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")


class LLMError(FactoryError):
    """LLM-layer failure. code is an LLMErrorCode."""


class PipelineError(FactoryError):
    """Pipeline-orchestration failure. code is a PipelineErrorCode."""


class VerificationError(FactoryError):
    """Per-record verification failure. code is a VerificationErrorCode."""


class RightsError(FactoryError):
    """Rights-validator failure. code is a RightsErrorCode."""


# ----- Routing helpers (used by verify.py to decide where to send records) -----

# These constants replace the string substrings used in v0.3.0's
# `pipeline/verify.py` routing logic. Maintaining a small set of named groups
# means renames are caught at type-check time rather than producing silent
# routing changes.

FIX_REQUIRED_ERRORS: set[VerificationErrorCode] = {
    VerificationErrorCode.SOURCE_SIMILARITY_WARNING,
    VerificationErrorCode.JUDGE_FIX_REQUIRED,
    VerificationErrorCode.LATEX_INVALID,
}

HUMAN_REVIEW_ERRORS: set[VerificationErrorCode] = {
    VerificationErrorCode.JUDGE_ERROR,
}

HARD_REJECT_ERRORS: set[VerificationErrorCode] = {
    VerificationErrorCode.SCHEMA_MISMATCH,
    VerificationErrorCode.UNKNOWN_RECORD_SHAPE,
    VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION,
    VerificationErrorCode.JUDGE_REJECT,
    VerificationErrorCode.BAD_PHRASE_DETECTED,
    VerificationErrorCode.MESSAGES_MISSING,
    VerificationErrorCode.BAD_MESSAGE_ROLES,
    VerificationErrorCode.ASSISTANT_TOO_SHORT,
    VerificationErrorCode.TEXT_TOO_SHORT,
}


def route_record(error_codes: list[VerificationErrorCode]) -> str:
    """Return one of: 'fix_required', 'human_review', 'rejected', 'accepted'.

    Routing priority:
        1. If any HARD_REJECT — reject.
        2. Else if any FIX_REQUIRED — fix_required.
        3. Else if any HUMAN_REVIEW — human_review.
        4. Else (empty list) — accepted.
    """
    code_set = set(error_codes)
    if code_set & HARD_REJECT_ERRORS:
        return "rejected"
    if code_set & FIX_REQUIRED_ERRORS:
        return "fix_required"
    if code_set & HUMAN_REVIEW_ERRORS:
        return "human_review"
    return "accepted"
