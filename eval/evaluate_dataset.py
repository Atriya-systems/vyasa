from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = []
    for line in Path(args.jsonl).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    status = Counter(r.get("metadata", {}).get("quality_status", "unknown") for r in rows)
    train_allowed = sum(1 for r in rows if r.get("metadata", {}).get("train_allowed") is True)
    lanes = Counter(r.get("metadata", {}).get("lane", "unknown") for r in rows)

    report = {
        "total": len(rows),
        "quality_status": dict(status),
        "train_allowed": train_allowed,
        "lanes": dict(lanes),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
