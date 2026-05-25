"""Tests for training/chat_templates.py — per-model chat template formatters."""
from __future__ import annotations

import pytest

from aspireace_mocf.training.chat_templates import (
    TEMPLATE_REGISTRY,
    detect_template_from_model_name,
    format_messages,
)


SAMPLE_MESSAGES = [
    {"role": "user", "content": "What is dimensional analysis?"},
    {"role": "assistant", "content": "Dimensional analysis checks consistency of equations."},
]


class TestTemplateDetection:
    @pytest.mark.parametrize("model_name,expected", [
        ("Qwen/Qwen3-8B", "chatml"),
        ("qwen2.5-7b-instruct", "chatml"),
        ("meta-llama/Meta-Llama-3.1-8B-Instruct", "llama3"),
        ("Llama-3-8B", "llama3"),
        ("microsoft/Phi-3.5-mini-instruct", "phi3"),
        ("phi-3-medium", "phi3"),
        ("mistralai/Mistral-7B-Instruct", "chatml"),
        ("mixtral-8x7b", "chatml"),
        ("some-unknown-model", "generic"),
    ])
    def test_detect_template_known_families(self, model_name, expected):
        assert detect_template_from_model_name(model_name) == expected


class TestFormatChatML:
    def test_chatml_format_with_system(self):
        out = format_messages(SAMPLE_MESSAGES, "chatml", system_prompt="You are a physics tutor.")
        assert "<|im_start|>system\nYou are a physics tutor.<|im_end|>" in out
        assert "<|im_start|>user\nWhat is dimensional analysis?<|im_end|>" in out
        assert "<|im_start|>assistant\nDimensional analysis" in out
        assert out.endswith("<|im_start|>assistant\n")

    def test_chatml_format_without_system(self):
        out = format_messages(SAMPLE_MESSAGES, "chatml")
        assert "<|im_start|>system" not in out
        assert "<|im_start|>user" in out

    def test_qwen_alias_uses_chatml(self):
        assert format_messages(SAMPLE_MESSAGES, "qwen3") == format_messages(SAMPLE_MESSAGES, "chatml")


class TestFormatLlama3:
    def test_llama3_format_with_system(self):
        out = format_messages(SAMPLE_MESSAGES, "llama3", system_prompt="Be concise.")
        assert out.startswith("<|begin_of_text|>")
        assert "<|start_header_id|>system<|end_header_id|>\n\nBe concise.<|eot_id|>" in out
        assert "<|start_header_id|>user<|end_header_id|>" in out
        assert out.endswith("<|start_header_id|>assistant<|end_header_id|>\n\n")

    def test_llama3_format_without_system(self):
        out = format_messages(SAMPLE_MESSAGES, "llama3")
        assert "<|start_header_id|>system" not in out


class TestFormatPhi3:
    def test_phi3_format(self):
        out = format_messages(SAMPLE_MESSAGES, "phi3", system_prompt="Tutor.")
        assert "<|system|>\nTutor.<|end|>" in out
        assert "<|user|>" in out
        assert "<|assistant|>" in out


class TestFormatGeneric:
    def test_generic_format(self):
        out = format_messages(SAMPLE_MESSAGES, "generic")
        assert "user: What is dimensional analysis?" in out
        assert "assistant: Dimensional analysis" in out


class TestErrorHandling:
    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown chat template"):
            format_messages(SAMPLE_MESSAGES, "not-a-real-template")

    def test_case_insensitive_template_key(self):
        a = format_messages(SAMPLE_MESSAGES, "CHATML")
        b = format_messages(SAMPLE_MESSAGES, "chatml")
        c = format_messages(SAMPLE_MESSAGES, "ChatML")
        assert a == b == c

    def test_template_registry_has_no_missing_implementations(self):
        # All registered keys must be callable.
        for key, fn in TEMPLATE_REGISTRY.items():
            assert callable(fn), f"template {key!r} not callable"
