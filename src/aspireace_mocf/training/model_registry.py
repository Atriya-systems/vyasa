"""Model registry — versioned ledger of trained model artifacts.

Purpose: every model you train has provenance — what data, what hyperparams,
what GPU, when, what eval score. The registry is the durable record. Without
it, six months from now you can't tell what was trained, on what, or why one
model is better than another.

Storage layout:

    artifacts/model_registry/
    ├── registry.jsonl                       append-only ledger of every model
    ├── <model_id>/
    │   ├── manifest.json                    detailed entry for this model
    │   ├── config.json                      training-config snapshot
    │   ├── eval_history.jsonl               append-only eval results over time
    │   └── weights_sha256.txt               sha256 of the LoRA/full weights
    └── ...

Why two files for the registry: ``registry.jsonl`` is a flat searchable index
(grep-friendly, append-only). ``<model_id>/manifest.json`` holds the detailed
record (with eval history, lifecycle status, etc.). The two are kept in sync
by the API — never edit manifest.json directly.

Status lifecycle:
    training → ready → deprecated
    training → failed (terminal)

A model in ``training`` is being fit; ``ready`` means the artifact exists +
passed at least one eval; ``deprecated`` means superseded (kept for
reproducibility); ``failed`` means training did not complete.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.hashing import sha256_file
from aspireace_mocf.utils.jsonio import read_jsonl, write_json, write_jsonl
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


class ModelStatus(str, Enum):
    TRAINING = "training"
    READY = "ready"
    DEPRECATED = "deprecated"
    FAILED = "failed"


@dataclass
class TrainingConfig:
    """Snapshot of the hyperparameters used to train a model."""

    base_model: str
    method: str  # "lora_sft" | "lora_cpt" | "full_sft" | etc.
    learning_rate: float
    max_steps: int
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    lora_r: int | None = None
    lora_alpha: int | None = None
    lora_dropout: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingMetadata:
    """Per-run training metadata. Captured once when register_model is called
    with status=ready."""

    started_at_utc: str
    finished_at_utc: str
    gpu_type: str  # e.g. "RTX_5060_8GB" or "Runpod_A10G_24GB"
    gpu_count: int
    total_train_steps: int
    final_train_loss: float | None
    final_eval_loss: float | None
    estimated_total_tokens: int | None = None
    estimated_compute_cost_inr: float | None = None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _registry_dir(root: Path = Path("artifacts/model_registry")) -> Path:
    return Path(root)


def _registry_file(root: Path = Path("artifacts/model_registry")) -> Path:
    return _registry_dir(root) / "registry.jsonl"


def _model_dir(model_id: str, root: Path = Path("artifacts/model_registry")) -> Path:
    return _registry_dir(root) / model_id


def _hash_artifact(artifact_path: Path) -> str:
    """SHA-256 over the artifact. If it's a file, hash the file. If it's a
    directory, hash a manifest of (filename, sha256) entries for stability."""
    artifact_path = Path(artifact_path)
    if artifact_path.is_file():
        return sha256_file(artifact_path)
    if artifact_path.is_dir():
        # Stable hash: SHA-256 over sorted "filename:sha256" lines.
        entries = []
        for p in sorted(artifact_path.rglob("*")):
            if p.is_file():
                rel = p.relative_to(artifact_path).as_posix()
                entries.append(f"{rel}:{sha256_file(p)}")
        composite = "\n".join(entries).encode("utf-8")
        return hashlib.sha256(composite).hexdigest()
    raise FileNotFoundError(f"Artifact path does not exist: {artifact_path}")


def register_model(
    *,
    model_id: str,
    base_model: str,
    method: str,
    training_config: TrainingConfig,
    artifact_path: Path,
    dataset_id: str,
    dataset_sha256: str,
    training_metadata: TrainingMetadata | None = None,
    status: str = "ready",
    notes: str = "",
    root: Path = Path("artifacts/model_registry"),
) -> dict[str, Any]:
    """Register a new trained model in the ledger.

    Args:
        model_id: unique identifier, e.g. ``tutor_qwen3-8b_phy_v1_20260601``.
        base_model: e.g. ``Qwen/Qwen3-8B``.
        method: ``lora_sft`` | ``lora_cpt`` | ``full_sft`` | ...
        training_config: hyperparameter snapshot.
        artifact_path: path to the trained weights (file or directory).
        dataset_id: links to data_prep manifest at
            ``artifacts/training_data/<dataset_id>/manifest.json``.
        dataset_sha256: hash of the training dataset (provenance lock).
        training_metadata: GPU + time + loss snapshot. None during training
            phase; set when promoting to ready.
        status: lifecycle status, default 'ready'.
        notes: free-form text for the human reader.
        root: registry root directory.

    Returns:
        The manifest dict written to ``<model_id>/manifest.json``.

    Raises:
        FileExistsError: if ``model_id`` already exists in the registry.
        ValueError: if status is not a valid ModelStatus.
        FileNotFoundError: if artifact_path doesn't exist (when status != training).
    """
    if status not in {s.value for s in ModelStatus}:
        raise ValueError(
            f"Invalid status {status!r}. Allowed: {[s.value for s in ModelStatus]}"
        )

    model_dir = _model_dir(model_id, root)
    if model_dir.exists() and (model_dir / "manifest.json").exists():
        raise FileExistsError(
            f"model_id {model_id!r} already exists at {model_dir}. "
            f"Use update_model_eval/set_model_status, or pick a different model_id."
        )

    model_dir.mkdir(parents=True, exist_ok=True)

    weights_sha = ""
    if status != "training":
        # Artifact must exist by now.
        weights_sha = _hash_artifact(artifact_path)
        (model_dir / "weights_sha256.txt").write_text(weights_sha, encoding="utf-8")

    manifest = {
        "model_id": model_id,
        "base_model": base_model,
        "method": method,
        "status": status,
        "registered_at_utc": _now(),
        "artifact_path": str(artifact_path),
        "weights_sha256": weights_sha,
        "dataset_id": dataset_id,
        "dataset_sha256": dataset_sha256,
        "training_config": asdict(training_config),
        "training_metadata": asdict(training_metadata) if training_metadata else None,
        "eval_runs": [],
        "best_overall_normalised": None,
        "notes": notes,
        "history": [
            {"event": "registered", "at_utc": _now(), "status": status},
        ],
    }

    # Write per-model manifest + config.
    write_json(model_dir / "manifest.json", manifest)
    write_json(model_dir / "config.json", asdict(training_config))

    # Append to flat registry.
    _append_registry_index(
        root,
        {
            "model_id": model_id,
            "base_model": base_model,
            "method": method,
            "status": status,
            "registered_at_utc": manifest["registered_at_utc"],
            "weights_sha256": weights_sha,
            "dataset_id": dataset_id,
        },
    )
    _log.info(
        "model_registered",
        model_id=model_id,
        base_model=base_model,
        method=method,
        status=status,
        weights_sha256=weights_sha[:16] + "..." if weights_sha else "",
    )
    return manifest


def _append_registry_index(root: Path, entry: dict[str, Any]) -> None:
    """Append an entry to the flat registry.jsonl index."""
    path = _registry_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_models(
    *,
    status: str | None = None,
    root: Path = Path("artifacts/model_registry"),
) -> list[dict[str, Any]]:
    """Return the registry index, optionally filtered by status.

    Note: the index is a denormalised snapshot. Status changes update the
    index (by appending a new line); the latest line per model_id wins.
    """
    path = _registry_file(root)
    if not path.exists():
        return []
    # Read all rows, keep latest per model_id.
    latest: dict[str, dict[str, Any]] = {}
    for entry in read_jsonl(path):
        latest[entry["model_id"]] = entry
    rows = list(latest.values())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows


def get_model(
    model_id: str,
    root: Path = Path("artifacts/model_registry"),
) -> dict[str, Any]:
    """Load the full per-model manifest. Raises FileNotFoundError if unknown."""
    manifest_path = _model_dir(model_id, root) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"model_id {model_id!r} not in registry. "
            f"Known: {[m['model_id'] for m in list_models(root=root)]}"
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def update_model_eval(
    model_id: str,
    *,
    eval_run_id: str,
    golden_set_version: str,
    aggregate_scores: dict[str, float],
    root: Path = Path("artifacts/model_registry"),
) -> dict[str, Any]:
    """Append an eval result to a model's history. Updates best_overall_normalised
    if this run beat the previous best.

    Returns the updated manifest.
    """
    manifest = get_model(model_id, root)
    overall = float(aggregate_scores.get("overall_normalised", 0.0))
    entry = {
        "eval_run_id": eval_run_id,
        "golden_set_version": golden_set_version,
        "aggregate_scores": aggregate_scores,
        "evaluated_at_utc": _now(),
    }
    manifest["eval_runs"].append(entry)

    prev_best = manifest.get("best_overall_normalised")
    if prev_best is None or overall > prev_best:
        manifest["best_overall_normalised"] = overall
        manifest["history"].append({
            "event": "new_best_eval",
            "at_utc": _now(),
            "eval_run_id": eval_run_id,
            "overall_normalised": overall,
        })

    manifest_path = _model_dir(model_id, root) / "manifest.json"
    write_json(manifest_path, manifest)

    # Also append to per-model eval_history.jsonl for grep-friendly access.
    eval_history_path = _model_dir(model_id, root) / "eval_history.jsonl"
    with eval_history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _log.info(
        "model_eval_recorded",
        model_id=model_id,
        eval_run_id=eval_run_id,
        overall_normalised=overall,
        is_new_best=(prev_best is None or overall > prev_best),
    )
    return manifest


def set_model_status(
    model_id: str,
    new_status: str,
    *,
    reason: str = "",
    root: Path = Path("artifacts/model_registry"),
) -> dict[str, Any]:
    """Move a model through the lifecycle (training → ready → deprecated).

    Raises ValueError on invalid status transitions.
    """
    if new_status not in {s.value for s in ModelStatus}:
        raise ValueError(
            f"Invalid status {new_status!r}. Allowed: {[s.value for s in ModelStatus]}"
        )

    manifest = get_model(model_id, root)
    old_status = manifest["status"]

    # Allowed transitions
    allowed: dict[str, set[str]] = {
        "training": {"ready", "failed"},
        "ready": {"deprecated"},
        "deprecated": set(),
        "failed": set(),
    }
    if new_status not in allowed.get(old_status, set()):
        raise ValueError(
            f"Invalid status transition for model {model_id!r}: "
            f"{old_status!r} → {new_status!r}. "
            f"Allowed from {old_status!r}: {allowed.get(old_status, set())}"
        )

    manifest["status"] = new_status
    manifest["history"].append({
        "event": "status_changed",
        "at_utc": _now(),
        "from": old_status,
        "to": new_status,
        "reason": reason,
    })
    write_json(_model_dir(model_id, root) / "manifest.json", manifest)
    _append_registry_index(
        root,
        {
            "model_id": model_id,
            "base_model": manifest["base_model"],
            "method": manifest["method"],
            "status": new_status,
            "registered_at_utc": manifest["registered_at_utc"],
            "weights_sha256": manifest["weights_sha256"],
            "dataset_id": manifest["dataset_id"],
        },
    )
    _log.info(
        "model_status_changed",
        model_id=model_id,
        from_status=old_status,
        to_status=new_status,
        reason=reason,
    )
    return manifest


def verify_artifact_integrity(
    model_id: str,
    root: Path = Path("artifacts/model_registry"),
) -> bool:
    """Re-hash the artifact and compare to the registered sha. Returns True if
    they match. Use for tamper detection or post-restore validation.

    Raises FileNotFoundError if model or artifact is missing.
    """
    manifest = get_model(model_id, root)
    artifact_path = Path(manifest["artifact_path"])
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Artifact missing for model {model_id!r} at {artifact_path}"
        )
    actual = _hash_artifact(artifact_path)
    expected = manifest.get("weights_sha256", "")
    matches = actual == expected
    if not matches:
        _log.error(
            "artifact_integrity_failed",
            model_id=model_id,
            expected_sha=expected,
            actual_sha=actual,
        )
    return matches
