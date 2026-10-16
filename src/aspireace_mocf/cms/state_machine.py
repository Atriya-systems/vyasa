"""CMS state machine — enforced lifecycle transitions per canonical §Q2.

Lifecycle:

    draft → machine_validated → sme_reviewed → senior_approved → published
              ↘                                                     ↘
                       flagged ─────────────────────────────────→ retired

Transition rules:
- Roles authorized to perform a transition are encoded per-edge.
- ``flagged`` can be reached from ANY state (any reviewer / student can flag).
- ``retired`` is a terminal state; nothing transitions back.
- ``published`` requires train_allowed alignment (set true if record is in a
  trainable lane; else stays false).

Every transition writes to ``state_transitions`` and the resulting state is
committed to ``content_records.state`` atomically.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from aspireace_mocf.cms.storage import _now, connect
from aspireace_mocf.utils.errors import FactoryError
from aspireace_mocf.utils.logging import get_logger

_log = get_logger(__name__)


class ContentState(StrEnum):
    DRAFT = "draft"
    MACHINE_VALIDATED = "machine_validated"
    SME_REVIEWED = "sme_reviewed"
    SENIOR_APPROVED = "senior_approved"
    PUBLISHED = "published"
    FLAGGED = "flagged"
    RETIRED = "retired"


class ActorRole(StrEnum):
    SYSTEM = "system"          # automated machine validation
    JUNIOR_TEACHER = "junior"  # can stage for senior approval
    SENIOR_TEACHER = "senior"  # can flip train_allowed; only ones who can senior_approved
    HOD = "HOD"                # can publish + retire
    STUDENT = "student"        # can flag only
    PRODUCT = "product"        # can publish app-content + retire
    ADMIN = "admin"            # can do anything (escape hatch)


# Allowed transitions: keyed by (from_state, to_state) → set of authorized roles
# An empty set means "no transition allowed."
TRANSITIONS: dict[tuple[str, str], set[str]] = {
    (ContentState.DRAFT, ContentState.MACHINE_VALIDATED): {ActorRole.SYSTEM, ActorRole.ADMIN},
    (ContentState.DRAFT, ContentState.FLAGGED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.STUDENT, ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    (ContentState.MACHINE_VALIDATED, ContentState.SME_REVIEWED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.HOD, ActorRole.ADMIN},
    (ContentState.MACHINE_VALIDATED, ContentState.FLAGGED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.STUDENT, ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    (ContentState.SME_REVIEWED, ContentState.SENIOR_APPROVED): {ActorRole.SENIOR_TEACHER, ActorRole.HOD, ActorRole.ADMIN},
    (ContentState.SME_REVIEWED, ContentState.FLAGGED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.STUDENT, ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    (ContentState.SENIOR_APPROVED, ContentState.PUBLISHED): {ActorRole.SENIOR_TEACHER, ActorRole.HOD, ActorRole.PRODUCT, ActorRole.ADMIN},
    (ContentState.SENIOR_APPROVED, ContentState.FLAGGED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.STUDENT, ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    (ContentState.PUBLISHED, ContentState.FLAGGED): {ActorRole.JUNIOR_TEACHER, ActorRole.SENIOR_TEACHER, ActorRole.STUDENT, ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    (ContentState.PUBLISHED, ContentState.RETIRED): {ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
    # Flagged records can be EITHER promoted back to senior_approved (after fix)
    # OR retired (if irrecoverable).
    (ContentState.FLAGGED, ContentState.SENIOR_APPROVED): {ActorRole.SENIOR_TEACHER, ActorRole.HOD, ActorRole.ADMIN},
    (ContentState.FLAGGED, ContentState.RETIRED): {ActorRole.HOD, ActorRole.ADMIN, ActorRole.PRODUCT},
}


# States that, when entered, set train_allowed=true. Other states leave it false.
TRAIN_ALLOWED_STATES: frozenset[str] = frozenset({
    ContentState.SENIOR_APPROVED,
    ContentState.PUBLISHED,
})


# Trainable lanes — only these can have train_allowed flip true even at
# senior_approved/published. App-content lanes can be published but not trained on.
TRAINABLE_LANES: frozenset[str] = frozenset({
    "base_subject",
    "tutor_app",
    "content_generator",
})


class TransitionError(FactoryError):
    """Invalid state transition (illegal edge or unauthorized actor)."""


class TransitionErrorCode(StrEnum):
    UNKNOWN_RECORD = "unknown_record"
    ILLEGAL_TRANSITION = "illegal_transition"
    UNAUTHORIZED_ROLE = "unauthorized_role"
    SAME_STATE = "same_state"


def is_allowed(from_state: str, to_state: str, role: str) -> bool:
    """True if (from_state → to_state) is allowed for actors of `role`."""
    allowed_roles = TRANSITIONS.get((from_state, to_state), set())
    return role in allowed_roles


def allowed_next_states(from_state: str, role: str) -> list[str]:
    """All states `role` could move a record from `from_state` to."""
    return [
        to for (fr, to), roles in TRANSITIONS.items()
        if fr == from_state and role in roles
    ]


def transition(
    content_id: str,
    *,
    to_state: str,
    actor_id: str,
    actor_role: str,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Move a content record from its current state to ``to_state``.

    Validates: record exists, transition is legal, actor is authorized.
    Atomic: state change + audit log entry happen in one transaction.

    Returns updated record dict.
    Raises TransitionError on invalid transition / role / unknown record.
    """
    now = _now()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT content_id, state, lane, train_allowed FROM content_records WHERE content_id = ?",
            (content_id,),
        ).fetchone()
        if row is None:
            raise TransitionError(
                code=TransitionErrorCode.UNKNOWN_RECORD,
                message=f"content_id {content_id!r} not in CMS catalog. Register it first.",
            )
        from_state = row["state"]
        if from_state == to_state:
            raise TransitionError(
                code=TransitionErrorCode.SAME_STATE,
                message=f"Record {content_id!r} already in state {to_state!r}.",
            )
        if (from_state, to_state) not in TRANSITIONS:
            raise TransitionError(
                code=TransitionErrorCode.ILLEGAL_TRANSITION,
                message=(
                    f"Illegal transition for {content_id!r}: "
                    f"{from_state!r} → {to_state!r}. "
                    f"Allowed from {from_state!r} for any role: "
                    f"{[to for (fr, to) in TRANSITIONS if fr == from_state]}"
                ),
            )
        if not is_allowed(from_state, to_state, actor_role):
            allowed_roles = TRANSITIONS[(from_state, to_state)]
            raise TransitionError(
                code=TransitionErrorCode.UNAUTHORIZED_ROLE,
                message=(
                    f"Role {actor_role!r} not authorized for "
                    f"{from_state!r} → {to_state!r}. "
                    f"Allowed roles: {sorted(allowed_roles)}"
                ),
            )

        # train_allowed flip happens iff entering a train-allowed state AND
        # the record's lane is trainable.
        train_allowed_new = (
            to_state in TRAIN_ALLOWED_STATES and row["lane"] in TRAINABLE_LANES
        )

        conn.execute(
            """
            UPDATE content_records
            SET state = ?, state_changed_at_utc = ?, updated_at_utc = ?,
                train_allowed = ?,
                quality_status = CASE
                    WHEN ? IN ('senior_approved', 'published') THEN 'sme_verified'
                    WHEN ? = 'retired' THEN 'retired'
                    WHEN ? = 'flagged' THEN 'flagged'
                    ELSE quality_status
                END
            WHERE content_id = ?
            """,
            (
                to_state, now, now,
                1 if train_allowed_new else 0,
                to_state, to_state, to_state,
                content_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO state_transitions
                (content_id, from_state, to_state, actor_id, actor_role,
                 reason, timestamp_utc, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_id, from_state, to_state, actor_id, actor_role,
                reason, now,
                json.dumps(metadata or {}, ensure_ascii=False) if metadata else None,
            ),
        )
        updated = conn.execute(
            "SELECT * FROM content_records WHERE content_id = ?",
            (content_id,),
        ).fetchone()

    _log.info(
        "cms_state_transition",
        content_id=content_id,
        from_state=from_state,
        to_state=to_state,
        actor_id=actor_id,
        actor_role=actor_role,
        train_allowed_now=bool(updated["train_allowed"]),
    )
    return dict(updated)


def get_transition_history(content_id: str, db_path=None) -> list[dict[str, Any]]:
    """All transitions for one record, newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM state_transitions
            WHERE content_id = ?
            ORDER BY timestamp_utc DESC
            """,
            (content_id,),
        ).fetchall()
        return [dict(r) for r in rows]
