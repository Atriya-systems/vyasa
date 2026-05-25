from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    source_units: Path
    lanes: Path
    verified: Path
    queues: Path
    rag: Path
    offline: Path
    exports: Path
    reports: Path
    manifests: Path

    @classmethod
    def create(cls, run_id: str) -> "RunPaths":
        base = Path("runs") / run_id
        obj = cls(
            run_dir=base,
            source_units=base / "source_units",
            lanes=base / "lanes",
            verified=base / "verified",
            queues=base / "queues",
            rag=base / "rag",
            offline=base / "offline",
            exports=base / "exports",
            reports=base / "reports",
            manifests=base / "manifests",
        )
        for path in [obj.source_units, obj.lanes, obj.verified, obj.queues, obj.rag, obj.offline, obj.exports, obj.reports, obj.manifests]:
            path.mkdir(parents=True, exist_ok=True)
        (obj.exports / "training").mkdir(exist_ok=True)
        (obj.exports / "app_content").mkdir(exist_ok=True)
        (obj.exports / "rag").mkdir(exist_ok=True)
        (obj.exports / "offline").mkdir(exist_ok=True)
        (obj.exports / "manifests").mkdir(exist_ok=True)
        return obj
