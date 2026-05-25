"""Eval harness — run any model against the golden set, score, report.

Purpose: this is what tells you "trained tutor v2 is better than v1" or
"trained tutor v1 beats prompt-chained Anthropic baseline on JEE problems."
Without it, training is flying blind.

How it works:
1. Load a frozen golden set version (hash-pinned for reproducibility).
2. For each golden record:
   a. Format the query using the target model's chat template.
   b. Call the target model to generate a response.
   c. Call a STRONG LLM-judge (e.g. Claude Sonnet or GPT-4o) to score the
      model's response across 4 dimensions vs the ideal response.
3. Aggregate per-dimension / per-subject / per-chapter / per-difficulty.
4. Emit a JSON manifest + Markdown human-readable summary.
5. Optionally diff against a previous eval run to show delta (improvement /
   regression per dimension).

The target model and judge model are separate ``LLMClient`` instances so you
can evaluate a weak local model with a strong cloud judge.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
SLA: evaluate 200 golden records in <= 30 minutes when judge is cloud-hosted
     (the bottleneck is judge latency, not target latency).
"""
from __future__ import annotations

import datetime as _dt
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from aspireace_mocf.training.chat_templates import (
    detect_template_from_model_name,
    format_messages,
)
from aspireace_mocf.training.golden_set import load_version
from aspireace_mocf.utils.jsonio import write_json, write_jsonl
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


DIMENSIONS: tuple[str, ...] = (
    "subject_correctness",
    "teaching_quality",
    "source_grounding",
    "app_usefulness",
)


# ---------- protocols + types ----------


class ChatCompleter(Protocol):
    """Anything that takes a chat-style messages list and returns a string.

    This is the protocol the eval harness expects for both the target model
    and the judge model. ``LLMClient.chat_json`` doesn't quite fit (returns
    parsed JSON), but a thin adapter does — see ``make_chat_completer``.
    """

    def __call__(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class GoldenRecordResult:
    """Per-record eval result."""

    record_id: str
    subject: str
    chapter_no: int
    difficulty: str
    query: str
    ideal_response: str
    model_response: str
    judge_scores: dict[str, int]  # per-dimension 0-5
    judge_decision: str  # accept | fix_required | human_review | reject
    judge_issues: list[str]
    judge_recommended_fix: str
    score_normalised: dict[str, float] = field(default_factory=dict)
    error: str | None = None


@dataclass
class EvalReport:
    """Full eval-run report."""

    run_id: str
    target_model_name: str
    judge_model_name: str
    golden_set_version: str
    started_at_utc: str
    finished_at_utc: str
    total_records: int
    successful_records: int
    errored_records: int
    aggregate_scores: dict[str, float]
    per_subject_scores: dict[str, dict[str, float]]
    per_difficulty_scores: dict[str, dict[str, float]]
    record_results: list[GoldenRecordResult]


# ---------- judge prompt ----------


JUDGE_PROMPT_TEMPLATE = """You are a strict, subject-matter-expert evaluator scoring an AspireACE tutor LLM.

You receive THREE inputs:
  1. STUDENT QUERY — what was asked
  2. IDEAL RESPONSE — senior-teacher-authored gold-standard response
  3. MODEL RESPONSE — the tutor LLM under evaluation

Score the MODEL RESPONSE (NOT the ideal) on 4 dimensions, each integer 0-5:
  - subject_correctness: factual + mathematical correctness for NEET/JEE Indian high-school physics/chem/bio/math
  - teaching_quality: pedagogical clarity, structure, appropriate scaffolding for Class 11/12 students
  - source_grounding: faithfulness to physics/chem/bio/math principles; no hallucinated facts; matches NCERT-level treatment
  - app_usefulness: would a real student in the AspireACE app find this response useful for solving the next problem?

Decision rule:
  - accept           if ALL 4 dimensions are >= 4
  - fix_required     if at least one dimension is exactly 3 and repairable
  - human_review     if uncertain after careful evaluation
  - reject           if ANY dimension is <= 2

Return strict JSON ONLY (no markdown fences, no prose):

STUDENT QUERY:
<<<
{query}
>>>

IDEAL RESPONSE:
<<<
{ideal_response}
>>>

MODEL RESPONSE:
<<<
{model_response}
>>>

NOTES TO EVALUATOR (from the golden record author):
{notes_to_evaluator}
"""


# ---------- helpers ----------


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _ideal_score(record: dict[str, Any], dimension: str) -> int:
    return record.get("dimensions", {}).get(dimension, 5)


def _normalise(score: int, ideal: int) -> float:
    """Normalise to 0..1 against the ideal. >1 means model beat the ideal
    (rare but possible if the judge is strict on the ideal and lenient on
    the model; flag for inspection)."""
    if ideal <= 0:
        return 0.0
    return score / ideal


# ---------- single-record eval ----------


def evaluate_record(
    record: dict[str, Any],
    *,
    target: ChatCompleter,
    judge_json: Callable[[str], dict[str, Any]],
    system_prompt: str = "You are an AspireACE NEET/JEE subject tutor.",
) -> GoldenRecordResult:
    """Evaluate one golden record. Returns a structured result.

    Args:
        record: a golden record loaded from a frozen version.
        target: a chat completer for the model under evaluation. Takes a
            messages list and returns a string response.
        judge_json: a callable that takes a prompt and returns parsed JSON.
            Typically wraps ``LLMClient.chat_json``.
        system_prompt: system prompt prepended to the target's messages.
    """
    query = record["query"]
    ideal_response = record["ideal_response"]
    notes = record.get("notes_to_evaluator", "(none)")

    # Generate model response
    try:
        messages = [{"role": "user", "content": query}]
        model_response = target(messages)
    except Exception as exc:
        _log.error("target_call_failed", record_id=record["record_id"], error=str(exc))
        return GoldenRecordResult(
            record_id=record["record_id"],
            subject=record.get("subject", "_"),
            chapter_no=int(record.get("chapter_no", 0)),
            difficulty=record.get("difficulty", "_"),
            query=query,
            ideal_response=ideal_response,
            model_response="",
            judge_scores={d: 0 for d in DIMENSIONS},
            judge_decision="reject",
            judge_issues=[f"target_call_failed: {exc}"],
            judge_recommended_fix="",
            score_normalised={d: 0.0 for d in DIMENSIONS},
            error=f"target_call_failed: {exc}",
        )

    # Send to judge
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        ideal_response=ideal_response,
        model_response=model_response,
        notes_to_evaluator=notes,
    )
    try:
        judge_result = judge_json(judge_prompt)
    except Exception as exc:
        _log.error("judge_call_failed", record_id=record["record_id"], error=str(exc))
        return GoldenRecordResult(
            record_id=record["record_id"],
            subject=record.get("subject", "_"),
            chapter_no=int(record.get("chapter_no", 0)),
            difficulty=record.get("difficulty", "_"),
            query=query,
            ideal_response=ideal_response,
            model_response=model_response,
            judge_scores={d: 0 for d in DIMENSIONS},
            judge_decision="human_review",
            judge_issues=[f"judge_call_failed: {exc}"],
            judge_recommended_fix="",
            score_normalised={d: 0.0 for d in DIMENSIONS},
            error=f"judge_call_failed: {exc}",
        )

    scores = {d: int(judge_result.get(d, 0)) for d in DIMENSIONS}
    normalised = {d: _normalise(scores[d], _ideal_score(record, d)) for d in DIMENSIONS}

    return GoldenRecordResult(
        record_id=record["record_id"],
        subject=record.get("subject", "_"),
        chapter_no=int(record.get("chapter_no", 0)),
        difficulty=record.get("difficulty", "_"),
        query=query,
        ideal_response=ideal_response,
        model_response=model_response,
        judge_scores=scores,
        judge_decision=str(judge_result.get("decision", "human_review")),
        judge_issues=list(judge_result.get("issues", [])),
        judge_recommended_fix=str(judge_result.get("recommended_fix", "")),
        score_normalised=normalised,
        error=None,
    )


# ---------- aggregation ----------


def _aggregate(results: list[GoldenRecordResult], key_fn: Callable[[GoldenRecordResult], str]) -> dict[str, dict[str, float]]:
    """Group results by key_fn(result), return mean normalised score per dimension per group."""
    groups: dict[str, list[GoldenRecordResult]] = {}
    for r in results:
        if r.error:
            continue
        groups.setdefault(key_fn(r), []).append(r)
    out: dict[str, dict[str, float]] = {}
    for key, items in groups.items():
        per_dim: dict[str, float] = {}
        for d in DIMENSIONS:
            vals = [r.score_normalised.get(d, 0.0) for r in items]
            per_dim[d] = round(statistics.mean(vals), 4) if vals else 0.0
        per_dim["count"] = len(items)
        per_dim["overall_normalised"] = round(
            statistics.mean(per_dim[d] for d in DIMENSIONS), 4
        )
        out[key] = per_dim
    return out


def _aggregate_overall(results: list[GoldenRecordResult]) -> dict[str, float]:
    """Mean normalised score per dimension across all (non-errored) records."""
    valid = [r for r in results if not r.error]
    if not valid:
        return {d: 0.0 for d in DIMENSIONS}
    out: dict[str, float] = {}
    for d in DIMENSIONS:
        out[d] = round(statistics.mean(r.score_normalised.get(d, 0.0) for r in valid), 4)
    out["overall_normalised"] = round(statistics.mean(out[d] for d in DIMENSIONS), 4)
    return out


# ---------- full eval run ----------


def run_eval(
    *,
    run_id: str,
    golden_set_version: str,
    target_model_name: str,
    judge_model_name: str,
    target: ChatCompleter,
    judge_json: Callable[[str], dict[str, Any]],
    output_dir: Path = Path("eval/runs"),
    golden_set_root: Path = Path("eval/golden_sets"),
    system_prompt: str = "You are an AspireACE NEET/JEE subject tutor.",
) -> EvalReport:
    """Run a full eval across one golden set version. Returns the structured report.

    Writes report JSON + Markdown summary + per-record JSONL into
    ``output_dir/<run_id>/``.
    """
    started = _now()
    records = load_version(golden_set_version, golden_set_root=golden_set_root)
    _log.info(
        "eval_run_starting",
        run_id=run_id,
        target_model=target_model_name,
        judge_model=judge_model_name,
        golden_set_version=golden_set_version,
        total_records=len(records),
    )

    results: list[GoldenRecordResult] = []
    for r in records:
        result = evaluate_record(r, target=target, judge_json=judge_json, system_prompt=system_prompt)
        results.append(result)
        _log.info(
            "eval_record_done",
            record_id=result.record_id,
            errored=result.error is not None,
            overall=round(sum(result.score_normalised.get(d, 0.0) for d in DIMENSIONS) / len(DIMENSIONS), 3) if not result.error else 0,
        )

    finished = _now()
    aggregate = _aggregate_overall(results)
    per_subject = _aggregate(results, key_fn=lambda r: r.subject)
    per_difficulty = _aggregate(results, key_fn=lambda r: r.difficulty)

    report = EvalReport(
        run_id=run_id,
        target_model_name=target_model_name,
        judge_model_name=judge_model_name,
        golden_set_version=golden_set_version,
        started_at_utc=started,
        finished_at_utc=finished,
        total_records=len(records),
        successful_records=sum(1 for r in results if not r.error),
        errored_records=sum(1 for r in results if r.error),
        aggregate_scores=aggregate,
        per_subject_scores=per_subject,
        per_difficulty_scores=per_difficulty,
        record_results=results,
    )

    # Persist outputs
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # JSON manifest (slim — without record_results to keep loadable)
    write_json(run_dir / "eval_report.json", {
        "run_id": run_id,
        "target_model_name": target_model_name,
        "judge_model_name": judge_model_name,
        "golden_set_version": golden_set_version,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "total_records": report.total_records,
        "successful_records": report.successful_records,
        "errored_records": report.errored_records,
        "aggregate_scores": aggregate,
        "per_subject_scores": per_subject,
        "per_difficulty_scores": per_difficulty,
    })

    # Per-record JSONL
    write_jsonl(run_dir / "record_results.jsonl", [
        {
            "record_id": r.record_id,
            "subject": r.subject,
            "chapter_no": r.chapter_no,
            "difficulty": r.difficulty,
            "judge_scores": r.judge_scores,
            "judge_decision": r.judge_decision,
            "judge_issues": r.judge_issues,
            "judge_recommended_fix": r.judge_recommended_fix,
            "score_normalised": r.score_normalised,
            "error": r.error,
            "model_response_preview": r.model_response[:500],
        }
        for r in results
    ])

    # Human-readable Markdown summary
    md = _render_markdown_summary(report)
    (run_dir / "EVAL_SUMMARY.md").write_text(md, encoding="utf-8")

    _log.info(
        "eval_run_completed",
        run_id=run_id,
        aggregate=aggregate,
        successful=report.successful_records,
        errored=report.errored_records,
    )
    return report


def _render_markdown_summary(report: EvalReport) -> str:
    """Render the EvalReport as a human-readable Markdown summary."""
    lines: list[str] = [
        f"# Eval run: `{report.run_id}`",
        "",
        f"- **Target model:** `{report.target_model_name}`",
        f"- **Judge model:** `{report.judge_model_name}`",
        f"- **Golden set version:** `{report.golden_set_version}`",
        f"- **Started:** {report.started_at_utc}",
        f"- **Finished:** {report.finished_at_utc}",
        f"- **Records evaluated:** {report.total_records} ({report.successful_records} successful, {report.errored_records} errored)",
        "",
        "## Aggregate normalised scores",
        "",
        "| Dimension | Score (0-1) |",
        "|---|---:|",
    ]
    for d in DIMENSIONS:
        lines.append(f"| {d} | {report.aggregate_scores.get(d, 0.0):.3f} |")
    lines.append(f"| **overall** | **{report.aggregate_scores.get('overall_normalised', 0.0):.3f}** |")
    lines.append("")

    lines.append("## Per-subject scores")
    lines.append("")
    if report.per_subject_scores:
        header = "| Subject | " + " | ".join(DIMENSIONS) + " | overall | count |"
        sep = "|---|" + "|".join(["---:"] * (len(DIMENSIONS) + 2)) + "|"
        lines.append(header)
        lines.append(sep)
        for subj, scores in sorted(report.per_subject_scores.items()):
            row = f"| {subj} | " + " | ".join(f"{scores.get(d, 0.0):.3f}" for d in DIMENSIONS) + f" | {scores.get('overall_normalised', 0.0):.3f} | {int(scores.get('count', 0))} |"
            lines.append(row)
    else:
        lines.append("_(no successful records)_")
    lines.append("")

    lines.append("## Per-difficulty scores")
    lines.append("")
    if report.per_difficulty_scores:
        header = "| Difficulty | " + " | ".join(DIMENSIONS) + " | overall | count |"
        sep = "|---|" + "|".join(["---:"] * (len(DIMENSIONS) + 2)) + "|"
        lines.append(header)
        lines.append(sep)
        for diff, scores in sorted(report.per_difficulty_scores.items()):
            row = f"| {diff} | " + " | ".join(f"{scores.get(d, 0.0):.3f}" for d in DIMENSIONS) + f" | {scores.get('overall_normalised', 0.0):.3f} | {int(scores.get('count', 0))} |"
            lines.append(row)
    else:
        lines.append("_(no successful records)_")
    lines.append("")

    return "\n".join(lines)


# ---------- diff two eval reports ----------


def diff_eval_runs(report_a_path: Path, report_b_path: Path) -> dict[str, Any]:
    """Compute per-dimension delta from report_a to report_b. Use for showing
    whether tutor_v2 actually improved over tutor_v1.

    Returns:
        dict with keys: 'a', 'b', 'overall_delta', 'per_dim_delta', 'per_subject_delta'
    """
    a = json.loads(Path(report_a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(report_b_path).read_text(encoding="utf-8"))

    if a.get("golden_set_version") != b.get("golden_set_version"):
        _log.warning(
            "eval_diff_golden_set_mismatch",
            a_version=a.get("golden_set_version"),
            b_version=b.get("golden_set_version"),
            note="Diffing runs against different golden sets gives meaningless comparison.",
        )

    overall_delta = {
        d: round(b["aggregate_scores"].get(d, 0.0) - a["aggregate_scores"].get(d, 0.0), 4)
        for d in DIMENSIONS
    }
    overall_delta["overall_normalised"] = round(
        b["aggregate_scores"].get("overall_normalised", 0.0)
        - a["aggregate_scores"].get("overall_normalised", 0.0),
        4,
    )

    per_subject_delta: dict[str, dict[str, float]] = {}
    all_subjects = set(a.get("per_subject_scores", {}).keys()) | set(b.get("per_subject_scores", {}).keys())
    for s in all_subjects:
        a_s = a.get("per_subject_scores", {}).get(s, {})
        b_s = b.get("per_subject_scores", {}).get(s, {})
        per_subject_delta[s] = {
            d: round(b_s.get(d, 0.0) - a_s.get(d, 0.0), 4) for d in DIMENSIONS
        }

    return {
        "a": {
            "run_id": a.get("run_id"),
            "target_model_name": a.get("target_model_name"),
            "golden_set_version": a.get("golden_set_version"),
        },
        "b": {
            "run_id": b.get("run_id"),
            "target_model_name": b.get("target_model_name"),
            "golden_set_version": b.get("golden_set_version"),
        },
        "overall_delta": overall_delta,
        "per_subject_delta": per_subject_delta,
    }
