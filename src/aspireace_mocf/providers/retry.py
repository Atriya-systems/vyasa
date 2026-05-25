"""Retry / exponential backoff for LLM calls.

Purpose: transient LLM failures (rate limits, connection drops, brief 5xx) should
not kill an entire pipeline run. This module wraps LLM calls in a tenacity
retry decorator that backs off exponentially and respects retryable error
classes only.

Non-retryable errors (BadRequestError, schema rejection, etc.) propagate
immediately — retrying them would just waste time. See `utils.errors.LLMError`
for the taxonomy.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


# Errors we retry on. These are the OpenAI SDK's transient-class errors.
# BadRequestError is NOT in this list — that's an unrecoverable prompt/config
# error and retry would just keep failing.
RETRYABLE_LLM_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    # APIError covers 5xx etc. Be conservative — if a 4xx slips through here
    # it's still 1 retry, not many, because of stop_after_attempt below.
    APIError,
)


F = TypeVar("F", bound=Callable[..., Any])


def with_llm_retry(func: F) -> F:
    """Decorator: retry an LLM call on transient errors with exponential backoff.

    Retry policy:
        - max 4 attempts total (1 try + 3 retries)
        - exponential backoff: 1s, 2s, 4s, 8s capped
        - retryable: APIConnectionError, APITimeoutError, RateLimitError, APIError
        - non-retryable: BadRequestError, custom LLMError, anything else

    Usage:
        @with_llm_retry
        def chat_json(self, prompt, ...): ...
    """
    return retry(  # type: ignore[return-value]
        retry=retry_if_exception_type(RETRYABLE_LLM_ERRORS),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(4),
        before_sleep=before_sleep_log(_log, log_level=30),  # 30 = WARNING
        reraise=True,
    )(func)
