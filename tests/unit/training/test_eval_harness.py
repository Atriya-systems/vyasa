"""Tests for training/eval_harness.py — model vs golden set scoring."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.training.eval_harness import (
    DIMENSIONS,
    _aggregate_overall,
    _normalise,
    diff_eval_runs,
    evaluate_record,
    run_eval,
)
from aspireace_mocf.training.golden_set import append_record, freeze_version


# ---------- helpers ----------


def _golden(**overrides):
    record = {
        "record_id": "GOLD_001",
        "query": "What is dimensional analysis?",
        "ideal_response": (
            "Dimensional analysis checks the consistency of physical equations by comparing "
            "the dimensions of each term. Useful for catching errors and deriving relations up "
            "to a dimensionless constant."
        ),
        "subject": "Physics",
        "chapter_no": 1,
        "chapter_name": "Units and Measurements",
        "topic": "Dimensional Analysis",
        "difficulty": "basic",
        "dimensions": {
            "subject_correctness": 5,
            "teaching_quality": 5,
            "source_grounding": 5,
            "app_usefulness": 5,
        },
        "author_teacher_id": "teacher_ashwin",
        "authored_at_utc": "2026-05-25T10:00:00+00:00",
    }
    record.update(overrides)
    return record


def make_target(response: str = "A canned tutor response with enough length to be evaluated."):
    """Return a ChatCompleter-compatible callable that always returns ``response``."""
    def _target(messages):
        return response
    return _target


def make_judge(scores=None, decision="accept"):
    """Return a judge callable that returns a canned JSON dict."""
    scores = scores or {d: 5 for d in DIMENSIONS}

    def _judge(prompt):
        return {
            **scores,
            "decision": decision,
            "issues": [],
            "recommended_fix": "",
        }
    return _judge


# ---------- normalisation ----------


def test_normalise_handles_perfect_match():
    assert _normalise(5, 5) == 1.0


def test_normalise_handles_partial():
    assert _normalise(3, 5) == 0.6


def test_normalise_handles_zero_ideal_safe():
    assert _normalise(5, 0) == 0.0  # protected against div-by-zero


# ---------- single record ----------


class TestEvaluateRecord:
    def test_happy_path_returns_perfect_score(self):
        result = evaluate_record(
            _golden(),
            target=make_target(),
            judge_json=make_judge(),
        )
        assert result.error is None
        assert result.record_id == "GOLD_001"
        assert result.judge_decision == "accept"
        for d in DIMENSIONS:
            assert result.judge_scores[d] == 5
            assert result.score_normalised[d] == 1.0

    def test_partial_score(self):
        result = evaluate_record(
            _golden(),
            target=make_target(),
            judge_json=make_judge(scores={
                "subject_correctness": 4,
                "teaching_quality": 3,
                "source_grounding": 5,
                "app_usefulness": 4,
            }),
        )
        assert result.judge_scores["teaching_quality"] == 3
        assert result.score_normalised["teaching_quality"] == 0.6
        assert result.score_normalised["subject_correctness"] == 0.8

    def test_target_failure_returns_error_result(self):
        def fail_target(messages):
            raise RuntimeError("LM Studio not running")
        result = evaluate_record(
            _golden(),
            target=fail_target,
            judge_json=make_judge(),
        )
        assert result.error is not None
        assert "target_call_failed" in result.error
        assert result.judge_decision == "reject"
        for d in DIMENSIONS:
            assert result.judge_scores[d] == 0

    def test_judge_failure_returns_error_result(self):
        def fail_judge(prompt):
            raise RuntimeError("judge model unreachable")
        result = evaluate_record(
            _golden(),
            target=make_target(),
            judge_json=fail_judge,
        )
        assert result.error is not None
        assert "judge_call_failed" in result.error
        assert result.judge_decision == "human_review"
        # model_response was successfully captured even though judge failed
        assert result.model_response  # non-empty


# ---------- aggregation ----------


class TestAggregateOverall:
    def test_empty_returns_zeros(self):
        out = _aggregate_overall([])
        for d in DIMENSIONS:
            assert out[d] == 0.0

    def test_only_errored_returns_zeros(self):
        # Create some errored results
        results = [
            evaluate_record(
                _golden(),
                target=lambda m: (_ for _ in ()).throw(RuntimeError("fail")),
                judge_json=make_judge(),
            )
            for _ in range(3)
        ]
        out = _aggregate_overall(results)
        # All errored — should be zeros
        for d in DIMENSIONS:
            assert out[d] == 0.0

    def test_mean_of_normalised(self):
        # 3 records, all perfect, then one with score 0
        results = []
        results.extend(
            evaluate_record(_golden(record_id=f"G_{i}"), target=make_target(), judge_json=make_judge())
            for i in range(3)
        )
        results.append(
            evaluate_record(
                _golden(record_id="G_low"),
                target=make_target(),
                judge_json=make_judge(scores={d: 0 for d in DIMENSIONS}, decision="reject"),
            )
        )
        out = _aggregate_overall(results)
        # 3 of 4 = 1.0, 1 of 4 = 0.0 → mean = 0.75
        assert out["subject_correctness"] == 0.75


# ---------- end-to-end run_eval ----------


class TestRunEval:
    def test_run_eval_produces_outputs(self, tmp_path):
        # Set up a golden set with 3 records.
        gs_root = tmp_path / "golden_sets"
        for i in range(3):
            append_record(
                record=_golden(record_id=f"G_{i:03d}"),
                golden_set_root=gs_root,
            )
        freeze_version(golden_set_root=gs_root)

        output_dir = tmp_path / "runs"
        report = run_eval(
            run_id="test_eval_001",
            golden_set_version="v1",
            target_model_name="qwen3-8b-test",
            judge_model_name="claude-test",
            target=make_target(),
            judge_json=make_judge(),
            output_dir=output_dir,
            golden_set_root=gs_root,
        )

        assert report.total_records == 3
        assert report.successful_records == 3
        assert report.errored_records == 0
        for d in DIMENSIONS:
            assert report.aggregate_scores[d] == 1.0

        # Files exist
        run_dir = output_dir / "test_eval_001"
        assert (run_dir / "eval_report.json").exists()
        assert (run_dir / "record_results.jsonl").exists()
        assert (run_dir / "EVAL_SUMMARY.md").exists()

        # Summary readable
        md = (run_dir / "EVAL_SUMMARY.md").read_text(encoding="utf-8")
        assert "test_eval_001" in md
        assert "qwen3-8b-test" in md
        assert "Physics" in md


# ---------- diff ----------


class TestDiffEvalRuns:
    def test_diff_shows_improvement(self, tmp_path):
        # Write two minimal eval report JSONs.
        report_a = {
            "run_id": "v1_eval",
            "target_model_name": "tutor-v1",
            "golden_set_version": "v1",
            "aggregate_scores": {d: 0.6 for d in DIMENSIONS},
            "per_subject_scores": {"Physics": {d: 0.6 for d in DIMENSIONS}},
        }
        report_a["aggregate_scores"]["overall_normalised"] = 0.6
        report_b = {
            "run_id": "v2_eval",
            "target_model_name": "tutor-v2",
            "golden_set_version": "v1",
            "aggregate_scores": {d: 0.8 for d in DIMENSIONS},
            "per_subject_scores": {"Physics": {d: 0.8 for d in DIMENSIONS}},
        }
        report_b["aggregate_scores"]["overall_normalised"] = 0.8

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        path_a.write_text(json.dumps(report_a), encoding="utf-8")
        path_b.write_text(json.dumps(report_b), encoding="utf-8")

        delta = diff_eval_runs(path_a, path_b)
        for d in DIMENSIONS:
            assert delta["overall_delta"][d] == pytest.approx(0.2)
        assert delta["overall_delta"]["overall_normalised"] == pytest.approx(0.2)
        assert delta["a"]["run_id"] == "v1_eval"
        assert delta["b"]["run_id"] == "v2_eval"

    def test_diff_with_regression(self, tmp_path):
        a = {
            "run_id": "v1",
            "golden_set_version": "v1",
            "aggregate_scores": {d: 0.8 for d in DIMENSIONS},
            "per_subject_scores": {},
        }
        a["aggregate_scores"]["overall_normalised"] = 0.8
        b = {
            "run_id": "v2",
            "golden_set_version": "v1",
            "aggregate_scores": {d: 0.5 for d in DIMENSIONS},
            "per_subject_scores": {},
        }
        b["aggregate_scores"]["overall_normalised"] = 0.5

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        path_a.write_text(json.dumps(a), encoding="utf-8")
        path_b.write_text(json.dumps(b), encoding="utf-8")

        delta = diff_eval_runs(path_a, path_b)
        # Negative delta — model regressed.
        assert all(delta["overall_delta"][d] < 0 for d in DIMENSIONS)
