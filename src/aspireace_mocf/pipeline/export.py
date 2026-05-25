from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl


def _split(rows: list[dict[str, Any]], eval_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n_eval = max(1, int(round(len(rows) * eval_ratio))) if len(rows) >= 5 else 0
    return rows[n_eval:], rows[:n_eval]


def export_training(input_file: Path, train_file: Path, eval_file: Path, settings: Settings, *, text_only: bool = False) -> dict[str, int]:
    rows = [r for r in read_jsonl(input_file) if r.get("metadata", {}).get("train_allowed") is True]
    train, eval_rows = _split(rows, settings.eval_ratio, settings.random_seed)
    if text_only:
        train = [{"text": r["text"]} for r in train if "text" in r]
        eval_rows = [{"text": r["text"]} for r in eval_rows if "text" in r]
    write_jsonl(train_file, train)
    write_jsonl(eval_file, eval_rows)
    return {"train": len(train), "eval": len(eval_rows)}


def export_app_content(app_lane_files: list[Path], output_dir: Path) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for file in app_lane_files:
        rows = read_jsonl(file)
        out = output_dir / file.name
        write_jsonl(out, rows)
        counts[file.stem] = len(rows)
    return counts


def copy_json_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def write_export_summary(path: Path, summary: dict[str, Any]) -> None:
    write_json(path, summary)
