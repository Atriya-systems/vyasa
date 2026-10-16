"""Authorization helpers for the CMS operations follow-up."""
from __future__ import annotations

from aspireace_mocf.cms.auth import AuthenticatedActor


def require_role(actor: AuthenticatedActor, *roles: str) -> None:
    if actor.actor_role not in roles:
        raise PermissionError(f"CMS role {actor.actor_role!r} is not authorized for this operation")
