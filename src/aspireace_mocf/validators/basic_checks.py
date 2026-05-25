"""Basic record-shape + content checks.

Purpose: catch obvious LLM slop before it reaches the rights gate or human
review. Cheap rule-based heuristics that don't need an LLM.

Bug fixes vs v0.3.0 baseline:
- Bug #12 fix: expanded bad-phrase library. The old version only caught two
  substrings ("as an ai", "source unit"). Real LLM-self-references include
  dozens of common patterns; we now cover the ones that show up in
  Qwen/Llama/Phi/GPT outputs.

Above-the-bar additions:
- Return `VerificationErrorCode` enum values (not raw strings) so routing in
  `pipeline/verify.py` can use set-membership checks instead of substring matches.
- Track which specific bad phrase fired for debugging (logged via verify).

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

from typing import Any

from aspireace_mocf.utils.errors import VerificationErrorCode


# Expanded bad-phrase library. Patterns LLMs use when self-referencing or
# leaking the prompt frame. Lowercased for case-insensitive matching.
# Sourced from observed Qwen3/Llama3/GPT outputs during initial smoke runs.
BAD_PHRASES_LOWER: tuple[str, ...] = (
    # Self-reference
    "as an ai",
    "as a language model",
    "as an assistant",
    "as an llm",
    "i am an ai",
    "i'm an ai",
    "i am a language model",
    "i'm a language model",
    "i cannot generate",
    "i can't generate",
    "i'm unable to",
    "i am unable to",
    "i'm not able to",
    "i am not able to",
    "i apologize, but",
    "i'm sorry, but",
    "i'm sorry but",
    "as requested,",
    "as you requested,",
    "as the assistant",
    # Prompt-frame leakage
    "source unit",
    "source_unit",
    "based on the source",
    "based on the provided source",
    "based on the given source",
    "according to the source",
    "from the source text",
    "according to the provided text",
    "the user wants",
    "the user is asking",
    # Schema leakage
    '"record_id": "temp"',
    '"unit_id": "temp"',
    '"card_id": "temp"',
    "your task is to",
    "you are asked to",
    "your role is",
    # Refusals
    "i cannot assist",
    "i can't assist",
    "i won't",
    "i will not",
    # Markdown frame leakage (when stripping fences didn't catch them)
    "```json",
    "```python",
    # Common Qwen padding tokens that leak through
    "<|endoftext|>",
    "<|im_start|>",
    "<|im_end|>",
)


def record_errors(record: dict[str, Any]) -> list[VerificationErrorCode]:
    """Return enum-typed verification errors for a single record.

    Caller (pipeline/verify.py) uses these enums for routing via
    `aspireace_mocf.utils.errors.route_record`. No string-substring matching.
    """
    errors: list[VerificationErrorCode] = []

    # Shape-based checks: training-lane records have `text` (base_subject) or
    # `messages` (tutor_app / content_generator); app-lane records have `body`.
    text_field = ""
    if "text" in record:
        text_field = record.get("text", "") or ""
        if len(text_field.split()) < 25:
            errors.append(VerificationErrorCode.TEXT_TOO_SHORT)
    elif "messages" in record:
        messages = record.get("messages", [])
        if not isinstance(messages, list) or len(messages) < 2:
            errors.append(VerificationErrorCode.MESSAGES_MISSING)
        else:
            if messages[0].get("role") != "user" or messages[1].get("role") != "assistant":
                errors.append(VerificationErrorCode.BAD_MESSAGE_ROLES)
            assistant_content = messages[1].get("content", "") if len(messages) > 1 else ""
            if len(assistant_content.split()) < 15:
                errors.append(VerificationErrorCode.ASSISTANT_TOO_SHORT)
            # For tutor/contentgen, the assistant message is the "text" we check
            # for bad phrases.
            text_field = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
    elif "body" in record:
        # App-content card. `body` is the actual text the student will see.
        text_field = record.get("body", "") or ""
    else:
        errors.append(VerificationErrorCode.UNKNOWN_RECORD_SHAPE)

    # Bad-phrase scan across whatever text field we found.
    if text_field:
        lower = text_field.lower()
        for phrase in BAD_PHRASES_LOWER:
            if phrase in lower:
                errors.append(VerificationErrorCode.BAD_PHRASE_DETECTED)
                break

    # Train-allowability sanity. An api-drafted record must NOT be marked
    # train_allowed unless it has been SME-verified. This is the second of
    # three checkpoints in the rights gate (the others are at generation and
    # at approval).
    meta = record.get("metadata", {})
    if (
        meta.get("drafted_by") == "api_model"
        and meta.get("train_allowed") is True
        and meta.get("quality_status") != "sme_verified"
    ):
        errors.append(VerificationErrorCode.API_DRAFT_TRAIN_ALLOWED_WITHOUT_SME_VERIFICATION)

    return errors
