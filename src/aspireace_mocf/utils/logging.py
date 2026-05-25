"""Structured logging — JSON lines with correlation IDs.

Purpose: replace ad-hoc `print()` calls + `tqdm`-only visibility with structured
log records that can be parsed by tools, filtered by run_id, and shipped to
log aggregators (Phase 4).

Output format: JSON Lines to stderr by default. Can be configured to write to a
file via `LOG_FILE` env var.

Above-the-bar additions:
- Correlation IDs (run_id, record_id, lane) flow through `bind()` so every
  call within a unit of work shares context.
- Latency capture via the structlog timestamp processor.
- Sensitive fields (api keys, source text bodies) are NEVER logged at INFO; only
  at DEBUG. Keep this honest — don't put student data, model weights, or
  authored content into log fields.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


_CONFIGURED = False


def _configure() -> None:
    """Configure structlog once per process. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(log_level)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # JSON Lines processor chain. Times are ISO-8601 UTC.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str) -> Any:
    """Return a configured structlog logger. Call from module top-level."""
    _configure()
    return structlog.get_logger(name)


def bind(**kwargs: Any) -> None:
    """Add fields to the current context — they appear in every subsequent log
    record from this thread/task until unbind."""
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind(*keys: str) -> None:
    """Remove fields from the current context."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Wipe all contextvars. Useful at the start of a CLI invocation."""
    structlog.contextvars.clear_contextvars()
