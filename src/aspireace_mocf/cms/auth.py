"""Small, fail-closed identity boundary for local CMS operator commands."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass


class CmsAuthenticationError(ValueError):
    """Raised when a CMS operator cannot be authenticated from configured users."""


@dataclass(frozen=True)
class AuthenticatedActor:
    actor_id: str
    actor_role: str


_ROLE_BY_SENIORITY = {"junior": "junior", "senior": "senior"}
_ALLOWED_ROLES = frozenset({"junior", "senior", "HOD", "product", "admin"})


def authenticate_reviewer(reviewer_id: str, password: str) -> AuthenticatedActor:
    """Authenticate against the managed ``REVIEWER_USERS`` registry.

    The caller never supplies a role. It is derived from the configured user
    record, which is the local Phase-1 authority already used by review_app.
    Missing or malformed configuration fails closed; there is no dev account on
    this CLI path.
    """
    raw_users = os.environ.get("REVIEWER_USERS", "")
    if not raw_users:
        raise CmsAuthenticationError("REVIEWER_USERS must be configured for CMS operator commands")
    try:
        users = json.loads(raw_users)
        user = users[reviewer_id]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CmsAuthenticationError("unknown CMS reviewer or invalid REVIEWER_USERS registry") from exc

    expected_hash = user.get("password_sha256")
    supplied_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if not isinstance(expected_hash, str) or not hmac.compare_digest(expected_hash, supplied_hash):
        raise CmsAuthenticationError("invalid CMS reviewer credentials")

    role = user.get("cms_role") or _ROLE_BY_SENIORITY.get(user.get("seniority"))
    if role not in _ALLOWED_ROLES:
        raise CmsAuthenticationError("CMS reviewer has no authorized lifecycle role")
    return AuthenticatedActor(actor_id=reviewer_id, actor_role=role)
