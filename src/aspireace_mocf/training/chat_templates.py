"""Chat template formatters — applies the right chat template per target model.

Purpose: training data lives in OpenAI-style ``{"messages": [...]}`` JSONL. For
SFT, that messages list needs to be flattened into a single string using the
target model's chat template (Qwen3 uses ChatML; Llama 3 uses its own; Phi 3
has yet another). HuggingFace's `tokenizer.apply_chat_template()` does this at
training time, but having explicit Python formatters here lets us:
- Test the formatted output independently of a tokenizer.
- Format queries for the eval harness (which doesn't run inside a trainer).
- Inspect what the model actually sees, for debugging.

This module is a thin reference layer. The training scripts themselves prefer
`tokenizer.apply_chat_template()` for the actual training pass — that's the
ground truth.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

from typing import Callable


# Each formatter takes a list of {"role": "...", "content": "..."} dicts and
# returns the model-specific flattened string. The optional second arg is the
# system prompt to inject at the top.


def _to_chatml(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """ChatML format used by Qwen, GPT-4 derivatives, and many open models."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append("<|im_start|>assistant\n")  # generation prompt
    return "\n".join(parts)


def _to_llama3(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """Llama 3 instruct format. See https://huggingface.co/blog/llama3#how-to-prompt-llama-3"""
    parts: list[str] = ["<|begin_of_text|>"]
    if system_prompt:
        parts.append(f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>")
    parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "".join(parts)


def _to_phi3(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """Phi 3.5 instruct format."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"<|system|>\n{system_prompt}<|end|>")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"<|{role}|>\n{content}<|end|>")
    parts.append("<|assistant|>\n")
    return "".join(parts)


def _to_generic_openai(messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
    """Fallback: plain-text role-prefixed format. Useful for inspection."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"system: {system_prompt}")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


TEMPLATE_REGISTRY: dict[str, Callable[..., str]] = {
    "chatml": _to_chatml,
    "qwen": _to_chatml,
    "qwen2": _to_chatml,
    "qwen2.5": _to_chatml,
    "qwen3": _to_chatml,
    "llama3": _to_llama3,
    "llama-3": _to_llama3,
    "llama-3.1": _to_llama3,
    "phi3": _to_phi3,
    "phi-3": _to_phi3,
    "phi-3.5": _to_phi3,
    "generic": _to_generic_openai,
    "openai": _to_generic_openai,
}


def detect_template_from_model_name(model_name: str) -> str:
    """Map a model name to a template key. Best-effort.

    Args:
        model_name: e.g. "Qwen/Qwen3-8B" or "meta-llama/Meta-Llama-3.1-8B-Instruct"

    Returns:
        Template key, e.g. "chatml". Falls back to "generic" if unrecognised.
    """
    lower = model_name.lower()
    if "qwen" in lower:
        return "chatml"
    if "llama" in lower:
        return "llama3"
    if "phi" in lower:
        return "phi3"
    if "mistral" in lower or "mixtral" in lower:
        return "chatml"  # Mistral/Mixtral chat models use a ChatML-ish format
    return "generic"


def format_messages(
    messages: list[dict[str, str]],
    template: str,
    system_prompt: str | None = None,
) -> str:
    """Format an OpenAI-style messages list using the named chat template.

    Raises ValueError for unknown templates.
    """
    key = template.lower().strip()
    if key not in TEMPLATE_REGISTRY:
        raise ValueError(
            f"Unknown chat template {template!r}. Known: {sorted(TEMPLATE_REGISTRY.keys())}"
        )
    return TEMPLATE_REGISTRY[key](messages, system_prompt)
