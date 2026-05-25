"""Token budget guard — fail fast if a prompt would exceed the model context.

Purpose: better to raise an explicit `PROMPT_TOO_LARGE` error than let the
provider silently truncate or return garbage. Uses a cheap character-based
heuristic by default (~4 chars/token for English mixed content); precise
tokenization can be wired in via `tiktoken` if needed (out-of-scope for M1).

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

from aspireace_mocf.utils.errors import LLMError, LLMErrorCode


# Model context window sizes (input tokens, before output reservation).
# Conservative defaults; raise if a specific model is bigger.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # LM Studio-served models (commonly used local quants)
    "qwen3-8b-instruct": 32_768,
    "qwen2.5-7b-instruct": 32_768,
    "qwen2.5-3b-instruct": 32_768,
    "phi-3.5-mini": 128_000,
    "llama-3.1-8b-instruct": 128_000,
    "mistral-7b-instruct": 32_768,
    # OpenAI / OpenAI-compat hosted
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    # Together / Fireworks / Groq commonly used
    "meta-llama/Meta-Llama-3.1-8B-Instruct": 128_000,
    "meta-llama/Meta-Llama-3.1-70B-Instruct": 128_000,
    "mixtral-8x7b": 32_768,
}

# Default for any model we don't know — assume 8K to be safe.
DEFAULT_CONTEXT_WINDOW = 8_192

# Approximate chars-per-token for mixed English + JSON content.
# Real number is ~4 for English prose, ~3 for code/JSON. Use 3.5 as a compromise
# that errs on the side of caution.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Cheap token estimate. Don't rely on for billing accuracy; rely on for
    'is this prompt obviously too big' decisions."""
    return int(len(text) / CHARS_PER_TOKEN) + 1


def context_window_for(model_name: str) -> int:
    """Return the context window in tokens for the given model name."""
    return MODEL_CONTEXT_WINDOWS.get(model_name.lower().strip(), DEFAULT_CONTEXT_WINDOW)


def guard_prompt_budget(prompt: str, model_name: str, max_tokens: int) -> None:
    """Raise LLMError(PROMPT_TOO_LARGE) if prompt + max_tokens exceeds context window.

    Args:
        prompt: the user prompt (system prompt overhead estimated separately).
        model_name: the model name (used to look up context window).
        max_tokens: the max_tokens output reservation that will be requested.

    Raises:
        LLMError(LLMErrorCode.PROMPT_TOO_LARGE)
    """
    context_window = context_window_for(model_name)
    estimated_prompt_tokens = estimate_tokens(prompt)
    # System prompt + JSON-schema overhead is ~200-500 tokens; reserve 1000 to be safe.
    overhead = 1000
    needed = estimated_prompt_tokens + overhead + max_tokens
    if needed > context_window:
        raise LLMError(
            code=LLMErrorCode.PROMPT_TOO_LARGE,
            message=(
                f"Prompt would need ~{needed} tokens (prompt={estimated_prompt_tokens} "
                f"+ overhead={overhead} + reserved_output={max_tokens}) but model "
                f"{model_name!r} only has {context_window} token context window. "
                f"Either chunk the source material, reduce max_tokens, or use a "
                f"larger-context model."
            ),
        )
