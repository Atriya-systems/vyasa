"""Regression tests for the M4 extraction and CMS review findings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from aspireace_mocf.cms.state_machine import transition
from aspireace_mocf.cms.storage import connect, get_record, upsert_record
from aspireace_mocf.pipeline.formula_extraction import extract_formulas
from aspireace_mocf.settings import load_settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_jsonl


def _formula() -> dict:
    return {
        "latex_expression": "v^2 = u^2 + 2as",
        "statement": "Final velocity squared relates displacement and constant acceleration.",
        "variables": [{"symbol": "v", "meaning": "final velocity", "unit": "m/s"}],
        "applicability_conditions": ["Constant acceleration"],
        "worked_example": "A car accelerates uniformly over a known displacement.",
        "dimensional_check": "Both sides have dimensions of velocity squared.",
        "derivation_chapter_ref": "Chapter 1",
        "applied_in_chapters": ["Chapter 2"],
        "exam_targets": ["JEE"],
        "priority": "must_know",
    }


class _FormulaLlm:
    def __init__(self, rows: list[object]):
        self.rows = rows
        self.prompts: list[str] = []

    def chat_json(self, prompt: str, **_: object) -> list[object]:
        self.prompts.append(prompt)
        return self.rows


@pytest.mark.parametrize("subject", ["Physics", "Chemistry", "Biology", "Mathematics"])
def test_formula_extraction_renders_each_subject_and_writes_output(tmp_path: Path, subject: str) -> None:
    units = tmp_path / "units.jsonl"
    accepted = tmp_path / "formulas.jsonl"
    rejected = tmp_path / "formula_rejected.jsonl"
    write_jsonl(
        units,
        [
            {
                "unit_id": "UNIT_001",
                "formulas": ["v = u + at"],
                "subject": subject,
                "chapter_no": 1,
                "exam_targets": ["JEE"],
                "source_id": "source-1",
            }
        ],
    )
    llm = _FormulaLlm([_formula()])
    result = extract_formulas(
        units_file=units,
        output_file=accepted,
        rejected_file=rejected,
        settings=replace(load_settings(), subject=subject),
        llm=llm,  # type: ignore[arg-type]
    )

    assert result == {"formulas_accepted": 1, "formulas_rejected": 0, "units_with_formulas": 1}
    assert len(read_jsonl(accepted)) == 1
    assert read_jsonl(rejected) == []
    assert llm.prompts and subject in llm.prompts[0]


def test_formula_extraction_rejects_bad_item_but_preserves_valid_rows(tmp_path: Path) -> None:
    units = tmp_path / "units.jsonl"
    accepted = tmp_path / "formulas.jsonl"
    rejected = tmp_path / "formula_rejected.jsonl"
    write_jsonl(units, [{"unit_id": "UNIT_001", "formulas": ["F = ma"], "subject": "Physics"}])
    result = extract_formulas(
        units_file=units,
        output_file=accepted,
        rejected_file=rejected,
        settings=replace(load_settings(), subject="Physics"),
        llm=_FormulaLlm([_formula(), 42]),  # type: ignore[arg-type]
    )

    assert result["formulas_accepted"] == 1
    assert result["formulas_rejected"] == 1
    assert len(read_jsonl(accepted)) == 1
    assert read_jsonl(rejected)[0]["error"] == "non_object_item"


def _payload(*, train_allowed: bool = False) -> dict:
    return {"body": "draft", "metadata": {"train_allowed": train_allowed, "quality_status": "published"}}


def test_cms_registration_rejects_published_and_scrubs_training_claim(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    with pytest.raises(ValueError, match="draft entry state"):
        upsert_record(
            content_id="bad", record_type="note", lane="tutor_app", payload=_payload(), state="published", db_path=db
        )

    record = upsert_record(
        content_id="safe", record_type="note", lane="tutor_app", payload=_payload(train_allowed=True), db_path=db
    )
    assert record["state"] == "draft"
    assert record["train_allowed"] == 0
    assert json.loads(record["payload_json"])["metadata"]["train_allowed"] is False
    assert json.loads(record["payload_json"])["metadata"]["quality_status"] == "draft"


def test_cms_registration_rolls_back_when_version_write_fails(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    with connect(db) as conn:
        conn.execute("""CREATE TRIGGER fail_version BEFORE INSERT ON content_versions
                        BEGIN SELECT RAISE(ABORT, 'injected version failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected version failure"):
        upsert_record(content_id="atomic", record_type="note", lane="tutor_app", payload=_payload(), db_path=db)
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM content_records").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM content_versions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM state_transitions").fetchone()[0] == 0


def test_cms_transition_rolls_back_when_audit_write_fails(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    upsert_record(content_id="atomic-transition", record_type="note", lane="tutor_app", payload=_payload(), db_path=db)
    with connect(db) as conn:
        conn.execute("""CREATE TRIGGER fail_transition BEFORE INSERT ON state_transitions
                        WHEN NEW.to_state = 'machine_validated'
                        BEGIN SELECT RAISE(ABORT, 'injected transition failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected transition failure"):
        transition(
            "atomic-transition", to_state="machine_validated", actor_id="machine", actor_role="system", db_path=db
        )
    assert get_record("atomic-transition", db)["state"] == "draft"
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM state_transitions").fetchone()[0] == 1


def test_authenticated_cli_registers_and_transitions_without_role_spoofing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from aspireace_mocf.cli import main

    password = "test-secret"
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    monkeypatch.setenv(
        "REVIEWER_USERS",
        json.dumps({"operator": {"password_sha256": password_hash, "cms_role": "admin", "subjects": ["Physics"]}}),
    )
    monkeypatch.setenv("CMS_REVIEWER_PASSWORD", password)
    records = tmp_path / "records.jsonl"
    db = tmp_path / "catalog.sqlite"
    write_jsonl(records, [{"card_id": "CARD_001", "body": "review me", "metadata": {"train_allowed": True}}])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aspireace-mocf",
            "cms-register",
            "--input",
            str(records),
            "--db",
            str(db),
            "--lane",
            "tutor_app",
            "--record-type",
            "note",
            "--reviewer-id",
            "operator",
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == {"registered": 1, "state": "draft"}
    assert get_record("CARD_001", db)["train_allowed"] == 0

    for state in ("machine_validated", "sme_reviewed", "senior_approved", "published"):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "aspireace-mocf",
                "cms-transition",
                "--content-id",
                "CARD_001",
                "--to-state",
                state,
                "--db",
                str(db),
                "--reviewer-id",
                "operator",
            ],
        )
        main()
        capsys.readouterr()
    record = get_record("CARD_001", db)
    assert record["state"] == "published"
    assert record["train_allowed"] == 1
