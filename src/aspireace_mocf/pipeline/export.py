"""Export — split SME-verified records into train/eval and copy app-content out.

Purpose: final step of the pipeline. Takes records that have passed all gates
(quality_status="sme_verified", train_allowed=true) and writes them to the
canonical export location for downstream consumers (training, app ingest).

Bug fixes vs v0.3.0 baseline:
- Bug #21 fix: silent record drop. Old code did
    `train = [{"text": r["text"]} for r in train if "text" in r]`
  silently dropping records without a `text` field. We now log a structured
  warning with count and a sample of the dropped record IDs.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


def _split(
    rows: list[dict[str, Any]], eval_ratio: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n_eval = max(1, int(round(len(rows) * eval_ratio))) if len(rows) >= 5 else 0
    return rows[n_eval:], rows[:n_eval]


def export_training(
    input_file: Path,
    train_file: Path,
    eval_file: Path,
    settings: Settings,
    *,
    text_only: bool = False,
) -> dict[str, int]:
    """Export SME-verified training records to train/eval JSONL.

    Filters to `train_allowed=true` only. If `text_only=True` (used for
    base_subject lane), strips records to bare `{"text": "..."}` and logs
    any records dropped for missing `text`.
    """
    all_rows = read_jsonl(input_file)
    rows = [r for r in all_rows if r.get("metadata", {}).get("train_allowed") is True]
    skipped_not_train_allowed = len(all_rows) - len(rows)
    if skipped_not_train_allowed:
        _log.warning(
            "export_skipped_not_train_allowed",
            count=skipped_not_train_allowed,
            input_file=str(input_file),
        )

    train, eval_rows = _split(rows, settings.eval_ratio, settings.random_seed)

    if text_only:
        # Bug #21 fix: log dropped records, don't silently swallow.
        train_filtered = [{"text": r["text"]} for r in train if "text" in r]
        dropped_train = len(train) - len(train_filtered)
        if dropped_train:
            sample_ids = [
                (r.get("metadata") or {}).get("record_id")
                for r in train if "text" not in r
            ][:5]
            _log.warning(
                "export_text_only_dropped_train",
                count=dropped_train,
                sample_record_ids=sample_ids,
                input_file=str(input_file),
            )
        train = train_filtered

        eval_filtered = [{"text": r["text"]} for r in eval_rows if "text" in r]
        dropped_eval = len(eval_rows) - len(eval_filtered)
        if dropped_eval:
            sample_ids = [
                (r.get("metadata") or {}).get("record_id")
                for r in eval_rows if "text" not in r
            ][:5]
            _log.warning(
                "export_text_only_dropped_eval",
                count=dropped_eval,
                sample_record_ids=sample_ids,
                input_file=str(input_file),
            )
        eval_rows = eval_filtered

    write_jsonl(train_file, train)
    write_jsonl(eval_file, eval_rows)
    return {"train": len(train), "eval": len(eval_rows)}


def export_app_content(app_lane_files: list[Path], output_dir: Path) -> dict[str, int]:
    """Copy each app-lane file to the export dir as-is."""
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for file in app_lane_files:
        rows = read_jsonl(file)
        out = output_dir / file.name
        write_jsonl(out, rows)
        counts[file.stem] = len(rows)
    return counts


def copy_json_file(src: Path, dst: Path) -> None:
    """Copy a small JSON binding file. Silent if src doesn't exist (logged once)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        _log.info("copy_json_file_src_missing", src=str(src), dst=str(dst))


def write_export_summary(path: Path, summary: dict[str, Any]) -> None:
    write_json(path, summary)
