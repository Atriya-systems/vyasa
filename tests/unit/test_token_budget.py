"""Tests for providers/token_budget.py — context-window guard."""
from __future__ import annotations

import pytest

from aspireace_mocf.providers.token_budget import (
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    MODEL_CONTEXT_WINDOWS,
    context_window_for,
    estimate_tokens,
    guard_prompt_budget,
)
from aspireace_mocf.utils.errors import LLMError, LLMErrorCode


def test_estimate_tokens_returns_int():
    assert isinstance(estimate_tokens("hello world"), int)


def test_estimate_tokens_scales_with_text_length():
    short = estimate_tokens("a")
    long = estimate_tokens("a" * 1000)
    assert long > short
    assert long >= 1000 // int(CHARS_PER_TOKEN + 1)


def test_context_window_known_model():
    assert context_window_for("qwen3-8b-instruct") == 32_768
    assert context_window_for("phi-3.5-mini") == 128_000


def test_context_window_unknown_model_falls_back_to_default():
    assert context_window_for("never-heard-of-this-model") == DEFAULT_CONTEXT_WINDOW


def test_context_window_case_insensitive():
    assert context_window_for("Qwen3-8B-Instruct") == context_window_for("qwen3-8b-instruct")


def test_guard_passes_for_small_prompt():
    # Small prompt should not raise.
    guard_prompt_budget("short prompt", model_name="qwen3-8b-instruct", max_tokens=1000)


def test_guard_raises_for_oversized_prompt():
    # Build a prompt that would exceed the context window.
    huge_prompt = "x" * (32_768 * 4)  # ~32k tokens of single chars + overhead = oversized
    with pytest.raises(LLMError) as exc_info:
        guard_prompt_budget(huge_prompt, model_name="qwen3-8b-instruct", max_tokens=9000)
    assert exc_info.value.code == LLMErrorCode.PROMPT_TOO_LARGE


def test_guard_message_contains_helpful_info():
    huge_prompt = "x" * (32_768 * 4)
    try:
        guard_prompt_budget(huge_prompt, model_name="qwen3-8b-instruct", max_tokens=9000)
    except LLMError as exc:
        msg = exc.message
        assert "qwen3-8b-instruct" in msg
        assert "32768" in msg or "32,768" in msg or "32_768" in msg
        # The error message should give actionable guidance.
        assert "chunk" in msg.lower() or "reduce" in msg.lower() or "larger" in msg.lower()
