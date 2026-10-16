"""Authenticated CMS service boundary used by operator commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aspireace_mocf.cms.auth import AuthenticatedActor
from aspireace_mocf.cms.state_machine import transition
from aspireace_mocf.cms.storage import upsert_record


def register_draft(
    *,
    content_id: str,
    record_type: str,
    lane: str,
    payload: dict[str, Any],
    actor: AuthenticatedActor,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Register content at the only safe entry state, ``draft``."""
    return upsert_record(
        content_id=content_id,
        record_type=record_type,
        lane=lane,
        payload=payload,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        db_path=db_path,
    )


def transition_authenticated(
    content_id: str,
    *,
    to_state: str,
    actor: AuthenticatedActor,
    reason: str = "",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply a lifecycle transition with identity/role bound by authentication."""
    return transition(
        content_id,
        to_state=to_state,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        reason=reason,
        db_path=db_path,
    )
