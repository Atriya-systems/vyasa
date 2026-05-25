from __future__ import annotations

from typing import Any


def record_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "text" in record:
        text = record.get("text", "")
        if len(text.split()) < 25:
            errors.append("text_too_short")
        if "as an ai" in text.lower() or "source unit" in text.lower():
            errors.append("bad_phrase")
    elif "messages" in record:
        messages = record.get("messages", [])
        if not isinstance(messages, list) or len(messages) < 2:
            errors.append("messages_missing")
        else:
            if messages[0].get("role") != "user" or messages[1].get("role") != "assistant":
                errors.append("bad_message_roles")
            if len(messages[1].get("content", "").split()) < 15:
                errors.append("assistant_too_short")
    else:
        errors.append("unknown_record_shape")

    meta = record.get("metadata", {})
    if meta.get("drafted_by") == "api_model" and meta.get("train_allowed") is True and meta.get("quality_status") != "sme_verified":
        errors.append("api_draft_train_allowed_without_sme_verification")
    return errors
