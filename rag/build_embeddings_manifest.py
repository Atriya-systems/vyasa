from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--embedding-model", default="local/default-embedding")
    args = parser.parse_args()

    count = sum(1 for line in Path(args.chunks).read_text(encoding="utf-8").splitlines() if line.strip())
    manifest = {
        "chunks": args.chunks,
        "chunk_count": count,
        "embedding_model": args.embedding_model,
        "status": "ready_for_embedding_job",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
