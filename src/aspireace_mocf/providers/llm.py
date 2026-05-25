"""LLM client — unified abstraction over LM Studio and OpenAI-compatible providers.

Purpose: single entry point for all LLM calls in the factory pipeline. Routes to
`LMStudioClient` or `OpenAICompatClient` based on `PROVIDER` env var. Handles JSON
schema response coercion, fallback when the provider doesn't support
`response_format=json_schema`, retry/backoff on transient failures, and
structured logging of every call.

Bug fixes vs v0.3.0 baseline:
- Bug #1: replaced bare `except Exception` swallow with specific exception
  handling. Falls back to no-`response_format` only when the API explicitly
  rejects the schema; preserves original error context if both calls fail.
  Logs the fallback (and root cause) instead of silently disabling validation.

Above-the-bar additions:
- Structured logging via `utils.logging` for every call (provider, model,
  prompt-hash, latency, token counts, fallback-taken).
- Token-budget guard via `providers.token_budget`: raises early if prompt would
  exceed the model's context window instead of letting the API truncate.
- Retry/backoff via `providers.retry` on transient errors (rate limit, 5xx,
  timeout).

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
SLA: one chat_json call <= 60s p95 for a 9k-token prompt on Qwen3-8B Q4_K_M.
Failure modes: see `utils.errors.LLMError` enum values.
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI
from openai import APIError, APIConnectionError, APITimeoutError, BadRequestError, RateLimitError

from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.errors import LLMError, LLMErrorCode
from aspireace_mocf.utils.logging import get_logger
from aspireace_mocf.providers.retry import with_llm_retry
from aspireace_mocf.providers.token_budget import estimate_tokens, guard_prompt_budget


_log = get_logger(__name__)


class LLMClient:
    """Unified LLM client. Constructs once per pipeline run; reused across all lanes."""

    def __init__(self, settings: Settings):
        self.settings = settings
        provider = settings.provider.strip().lower()
        if provider == "lmstudio":
            self.client = OpenAI(
                base_url=settings.lmstudio_base_url,
                api_key=settings.lmstudio_api_key,
            )
            self._provider_label = "lmstudio"
        elif provider == "openai":
            if not settings.openai_api_key:
                raise LLMError(
                    code=LLMErrorCode.CONFIG_MISSING_KEY,
                    message="OPENAI_API_KEY is missing. Set it in .env or environment.",
                )
            self.client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
            )
            self._provider_label = "openai"
        else:
            raise LLMError(
                code=LLMErrorCode.CONFIG_UNKNOWN_PROVIDER,
                message=f"Unsupported provider: {provider!r}. Use 'lmstudio' or 'openai'.",
            )
        _log.info(
            "llm_client_initialised",
            provider=self._provider_label,
            model=settings.model_name,
            base_url=settings.lmstudio_base_url if provider == "lmstudio" else settings.openai_base_url,
        )

    @with_llm_retry
    def chat_json(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        correlation_id: str | None = None,
    ) -> Any:
        """Send a chat-completion request expecting a JSON response.

        Args:
            prompt: user prompt content. System prompt is added by this method.
            schema: optional JSON Schema for structured output (`response_format=json_schema`).
            temperature: override settings.temperature for this call.
            max_tokens: override settings.max_tokens for this call.
            correlation_id: optional ID for log correlation (run_id, unit_id, etc.).

        Returns:
            Parsed JSON (typically dict or list per the prompt's expected shape).

        Raises:
            LLMError: with one of:
                - LLMErrorCode.PROMPT_TOO_LARGE — prompt exceeds context window
                - LLMErrorCode.PROVIDER_RATE_LIMIT — retries exhausted
                - LLMErrorCode.PROVIDER_TIMEOUT — retries exhausted
                - LLMErrorCode.PROVIDER_API_ERROR — non-retryable API error
                - LLMErrorCode.RESPONSE_INVALID_JSON — could not parse JSON
        """
        # Token-budget guard — raises if prompt is too large for the model context.
        # Better to fail fast than let the provider silently truncate.
        guard_prompt_budget(prompt, model_name=self.settings.model_name, max_tokens=max_tokens or self.settings.max_tokens)

        kwargs: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT_JSON},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": self.settings.max_tokens if max_tokens is None else max_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_response", "schema": schema, "strict": True},
            }

        log_ctx = {
            "provider": self._provider_label,
            "model": self.settings.model_name,
            "correlation_id": correlation_id,
            "prompt_chars": len(prompt),
            "prompt_tokens_est": estimate_tokens(prompt),
            "schema_provided": schema is not None,
        }

        start = time.monotonic()
        response = None
        fallback_taken = False
        original_schema_error: Exception | None = None

        # Bug #1 fix: specific exception handling, no bare `except Exception`.
        # `response_format=json_schema` is only supported on newer OpenAI models +
        # newer LM Studio versions. If the API rejects it (BadRequestError with
        # specific message), fall back to no-schema mode. Any OTHER error
        # propagates unchanged so retry/backoff can handle transient ones.
        try:
            response = self.client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # Determine if this is a response_format incompatibility vs a real
            # prompt-content error. The former is recoverable; the latter is not.
            err_str = str(exc).lower()
            if schema is not None and (
                "response_format" in err_str
                or "json_schema" in err_str
                or "unsupported" in err_str
                or "structured" in err_str
            ):
                original_schema_error = exc
                fallback_taken = True
                _log.warning(
                    "llm_response_format_unsupported_fallback",
                    error=str(exc),
                    **log_ctx,
                )
                kwargs.pop("response_format", None)
                # System prompt becomes stricter when schema isn't enforced API-side.
                kwargs["messages"][0]["content"] = _SYSTEM_PROMPT_JSON_STRICT
                try:
                    response = self.client.chat.completions.create(**kwargs)
                except Exception as second_exc:
                    raise LLMError(
                        code=LLMErrorCode.PROVIDER_API_ERROR,
                        message=(
                            f"LLM call failed twice — once with json_schema "
                            f"({original_schema_error}), once without ({second_exc})."
                        ),
                    ) from second_exc
            else:
                # Real prompt-content error; don't retry, don't swallow.
                _log.error("llm_bad_request", error=str(exc), **log_ctx)
                raise LLMError(
                    code=LLMErrorCode.PROVIDER_API_ERROR,
                    message=f"Provider rejected request: {exc}",
                ) from exc
        # APIConnectionError / APITimeoutError / RateLimitError / APIError are
        # caught by the `with_llm_retry` decorator and retried. If they reach
        # here, retries have been exhausted.

        latency = time.monotonic() - start
        if response is None:
            raise LLMError(
                code=LLMErrorCode.PROVIDER_API_ERROR,
                message="LLM client returned no response object (internal error).",
            )

        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None

        _log.info(
            "llm_call_completed",
            latency_s=round(latency, 3),
            fallback_taken=fallback_taken,
            response_chars=len(text),
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            **log_ctx,
        )

        cleaned = strip_json_fences(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            _log.error(
                "llm_response_invalid_json",
                error=str(exc),
                response_preview=cleaned[:500],
                fallback_taken=fallback_taken,
                **log_ctx,
            )
            raise LLMError(
                code=LLMErrorCode.RESPONSE_INVALID_JSON,
                message=(
                    f"LLM returned non-JSON content. fallback_taken={fallback_taken}. "
                    f"First 500 chars: {cleaned[:500]!r}"
                ),
            ) from exc


_SYSTEM_PROMPT_JSON = "Return only valid JSON. No markdown. No prose outside JSON."

# When response_format isn't supported API-side, the system prompt does the heavy
# lifting on JSON-strictness. Bias the model harder.
_SYSTEM_PROMPT_JSON_STRICT = (
    "You MUST return ONLY valid JSON. Your entire response must start with `{` or `[` "
    "and end with `}` or `]`. Do not wrap in markdown code fences. Do not add any "
    "prose, explanation, or commentary before or after the JSON. If the user prompt "
    "asks for an array, return an array (starts with `[`)."
)


def strip_json_fences(text: str) -> str:
    """Strip markdown code fences and leading `json` language tag from a response.

    Tolerates LLMs that wrap JSON in ```json ... ``` blocks despite system-prompt
    instructions not to.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text
