from __future__ import annotations

from pathlib import Path

import pytest

from aspireace_mocf.cms.auth import AuthenticatedActor
from aspireace_mocf.cms.comments import add_comment, add_flag, get_flags
from aspireace_mocf.cms.queues import assign_queue_entry, enqueue
from aspireace_mocf.cms.rollback import register_batch, rollback_batch
from aspireace_mocf.cms.storage import get_record, upsert_record
from aspireace_mocf.cms.version_history import rollback_to_version

ADMIN = AuthenticatedActor("ops-admin", "admin")
JUNIOR = AuthenticatedActor("junior-reviewer", "junior")


def _register(db: Path, content_id: str = "CARD_001") -> None:
    upsert_record(
        content_id=content_id,
        record_type="note",
        lane="tutor_app",
        payload={"body": "draft", "metadata": {}},
        db_path=db,
    )


def test_comments_and_flags_bind_actor_identity(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    _register(db)
    comment = add_comment(content_id="CARD_001", actor=JUNIOR, body="Needs a clearer example.", db_path=db)
    flag = add_flag(
        content_id="CARD_001", flag_type="pedagogical_issue", severity="warning", actor=JUNIOR, db_path=db
    )
    assert comment["author_id"] == "junior-reviewer"
    assert comment["author_role"] == "junior"
    assert flag["flagged_by"] == "junior-reviewer"
    assert get_flags("CARD_001", db_path=db)[0]["flagged_by_role"] == "junior"


def test_queue_assignment_cannot_spoof_privilege(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    _register(db)
    entry = enqueue(content_id="CARD_001", queue_type="ai_generated_pending", actor=JUNIOR, db_path=db)
    with pytest.raises(PermissionError):
        assign_queue_entry(entry["queue_id"], actor=JUNIOR, assigned_to="junior-reviewer", db_path=db)
    assigned = assign_queue_entry(entry["queue_id"], actor=ADMIN, assigned_to="junior-reviewer", db_path=db)
    assert assigned["state"] == "in_review"


def test_version_restore_requires_quarantine_before_mutating_history(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    _register(db)
    with pytest.raises(ValueError, match="flagged first"):
        rollback_to_version("CARD_001", 1, actor=ADMIN, reason="test", db_path=db)
    assert get_record("CARD_001", db)["state"] == "draft"


def test_batch_rollback_never_claims_success_after_record_failure(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    _register(db)
    register_batch(batch_id="batch-1", description="test", run_id=None, record_ids=["CARD_001", "missing"], db_path=db)
    result = rollback_batch("batch-1", actor=ADMIN, reason="bad source", db_path=db)
    assert result["rollback_state"] == "partial_failed"
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
