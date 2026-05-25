"""Tests for training/model_registry.py — versioned trained-model ledger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aspireace_mocf.training.model_registry import (
    ModelStatus,
    TrainingConfig,
    TrainingMetadata,
    get_model,
    list_models,
    register_model,
    set_model_status,
    update_model_eval,
    verify_artifact_integrity,
)


# ---------- helpers ----------


def _make_artifact(tmp_path: Path, name: str = "adapter") -> Path:
    """Create a dummy artifact directory with one file."""
    art = tmp_path / "artifacts" / name
    art.mkdir(parents=True, exist_ok=True)
    (art / "adapter_model.safetensors").write_bytes(b"fake LoRA weights")
    (art / "adapter_config.json").write_text(json.dumps({"r": 16}), encoding="utf-8")
    return art


def _good_config():
    return TrainingConfig(
        base_model="Qwen/Qwen3-8B",
        method="lora_sft",
        learning_rate=2e-4,
        max_steps=100,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        lora_r=16,
        lora_alpha=32,
        lora_dropout=0.05,
    )


def _good_metadata():
    return TrainingMetadata(
        started_at_utc="2026-05-25T10:00:00+00:00",
        finished_at_utc="2026-05-25T14:00:00+00:00",
        gpu_type="RTX_5060_8GB",
        gpu_count=1,
        total_train_steps=100,
        final_train_loss=0.8,
        final_eval_loss=0.95,
        estimated_total_tokens=1_500_000,
        estimated_compute_cost_inr=0.0,
    )


# ---------- register ----------


class TestRegisterModel:
    def test_register_creates_files(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        manifest = register_model(
            model_id="tutor_v1",
            base_model="Qwen/Qwen3-8B",
            method="lora_sft",
            training_config=_good_config(),
            artifact_path=artifact,
            dataset_id="dataset_001",
            dataset_sha256="abc123",
            training_metadata=_good_metadata(),
            status="ready",
            notes="first lora pass",
            root=root,
        )
        assert manifest["model_id"] == "tutor_v1"
        assert manifest["weights_sha256"]  # non-empty
        assert (root / "tutor_v1" / "manifest.json").exists()
        assert (root / "tutor_v1" / "config.json").exists()
        assert (root / "tutor_v1" / "weights_sha256.txt").exists()
        assert (root / "registry.jsonl").exists()

    def test_register_duplicate_raises(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="dup_model",
            base_model="x",
            method="lora_sft",
            training_config=_good_config(),
            artifact_path=artifact,
            dataset_id="d",
            dataset_sha256="h",
            root=root,
        )
        with pytest.raises(FileExistsError, match="already exists"):
            register_model(
                model_id="dup_model",
                base_model="x",
                method="lora_sft",
                training_config=_good_config(),
                artifact_path=artifact,
                dataset_id="d",
                dataset_sha256="h",
                root=root,
            )

    def test_register_with_invalid_status_raises(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        with pytest.raises(ValueError, match="Invalid status"):
            register_model(
                model_id="bad_status_model",
                base_model="x",
                method="lora_sft",
                training_config=_good_config(),
                artifact_path=artifact,
                dataset_id="d",
                dataset_sha256="h",
                status="not_a_real_status",
                root=tmp_path / "registry",
            )

    def test_register_training_status_doesnt_require_artifact(self, tmp_path):
        # A model in 'training' phase may not have artifact yet.
        root = tmp_path / "registry"
        nonexistent = tmp_path / "not_yet_exists"
        manifest = register_model(
            model_id="in_progress",
            base_model="x",
            method="lora_sft",
            training_config=_good_config(),
            artifact_path=nonexistent,
            dataset_id="d",
            dataset_sha256="h",
            status="training",
            root=root,
        )
        # weights_sha256 should be empty for training models.
        assert manifest["weights_sha256"] == ""

    def test_register_ready_with_missing_artifact_raises(self, tmp_path):
        root = tmp_path / "registry"
        nonexistent = tmp_path / "ghost"
        with pytest.raises(FileNotFoundError):
            register_model(
                model_id="ghost_model",
                base_model="x",
                method="lora_sft",
                training_config=_good_config(),
                artifact_path=nonexistent,
                dataset_id="d",
                dataset_sha256="h",
                status="ready",
                root=root,
            )


# ---------- list + get ----------


class TestListGetModel:
    def test_empty_registry(self, tmp_path):
        assert list_models(root=tmp_path / "registry") == []

    def test_list_after_register(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        models = list_models(root=root)
        assert len(models) == 1
        assert models[0]["model_id"] == "m1"

    def test_list_filtered_by_status(self, tmp_path):
        artifact = _make_artifact(tmp_path, name="art_a")
        artifact_b = _make_artifact(tmp_path, name="art_b")
        root = tmp_path / "registry"
        register_model(
            model_id="m_ready", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="ready", root=root,
        )
        register_model(
            model_id="m_train", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact_b,
            dataset_id="d", dataset_sha256="h", status="training", root=root,
        )
        assert {m["model_id"] for m in list_models(status="ready", root=root)} == {"m_ready"}
        assert {m["model_id"] for m in list_models(status="training", root=root)} == {"m_train"}

    def test_get_unknown_model_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not in registry"):
            get_model("ghost", root=tmp_path / "registry")

    def test_get_returns_full_manifest(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        m = get_model("m1", root=root)
        assert m["model_id"] == "m1"
        assert m["training_config"]["lora_r"] == 16
        assert "history" in m and len(m["history"]) >= 1


# ---------- update_eval ----------


class TestUpdateModelEval:
    def test_first_eval_sets_best(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        manifest = update_model_eval(
            "m1",
            eval_run_id="eval_001",
            golden_set_version="v1",
            aggregate_scores={"subject_correctness": 0.8, "overall_normalised": 0.75},
            root=root,
        )
        assert manifest["best_overall_normalised"] == 0.75
        assert len(manifest["eval_runs"]) == 1

    def test_second_eval_updates_best_if_better(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        update_model_eval(
            "m1", eval_run_id="eval_001", golden_set_version="v1",
            aggregate_scores={"overall_normalised": 0.6}, root=root,
        )
        manifest = update_model_eval(
            "m1", eval_run_id="eval_002", golden_set_version="v1",
            aggregate_scores={"overall_normalised": 0.85}, root=root,
        )
        assert manifest["best_overall_normalised"] == 0.85
        assert len(manifest["eval_runs"]) == 2
        # history should have new_best_eval events
        events = [h["event"] for h in manifest["history"]]
        assert events.count("new_best_eval") >= 2

    def test_worse_eval_doesnt_change_best(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        update_model_eval(
            "m1", eval_run_id="eval_001", golden_set_version="v1",
            aggregate_scores={"overall_normalised": 0.8}, root=root,
        )
        manifest = update_model_eval(
            "m1", eval_run_id="eval_002", golden_set_version="v1",
            aggregate_scores={"overall_normalised": 0.5}, root=root,
        )
        assert manifest["best_overall_normalised"] == 0.8

    def test_eval_history_file_appended(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        update_model_eval("m1", eval_run_id="e1", golden_set_version="v1",
                          aggregate_scores={"overall_normalised": 0.6}, root=root)
        update_model_eval("m1", eval_run_id="e2", golden_set_version="v1",
                          aggregate_scores={"overall_normalised": 0.7}, root=root)
        history_file = root / "m1" / "eval_history.jsonl"
        assert history_file.exists()
        lines = history_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2


# ---------- set_model_status ----------


class TestSetModelStatus:
    def test_training_to_ready(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="training", root=root,
        )
        m = set_model_status("m1", "ready", reason="training completed", root=root)
        assert m["status"] == "ready"
        events = [h["event"] for h in m["history"]]
        assert "status_changed" in events

    def test_training_to_failed(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="training", root=root,
        )
        m = set_model_status("m1", "failed", reason="OOM", root=root)
        assert m["status"] == "failed"

    def test_ready_to_deprecated(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="ready", root=root,
        )
        m = set_model_status("m1", "deprecated", reason="superseded by m2", root=root)
        assert m["status"] == "deprecated"

    def test_invalid_transition_raises(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="ready", root=root,
        )
        # ready → training is not allowed (would lose the trained artifact's provenance)
        with pytest.raises(ValueError, match="Invalid status transition"):
            set_model_status("m1", "training", root=root)

    def test_from_deprecated_no_transitions_allowed(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", status="ready", root=root,
        )
        set_model_status("m1", "deprecated", root=root)
        with pytest.raises(ValueError):
            set_model_status("m1", "ready", root=root)


# ---------- verify_artifact_integrity ----------


class TestVerifyArtifactIntegrity:
    def test_unchanged_artifact_verifies(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        assert verify_artifact_integrity("m1", root=root) is True

    def test_tampered_artifact_detected(self, tmp_path):
        artifact = _make_artifact(tmp_path)
        root = tmp_path / "registry"
        register_model(
            model_id="m1", base_model="x", method="lora_sft",
            training_config=_good_config(), artifact_path=artifact,
            dataset_id="d", dataset_sha256="h", root=root,
        )
        # Tamper.
        (artifact / "adapter_model.safetensors").write_bytes(b"different weights now")
        assert verify_artifact_integrity("m1", root=root) is False


# ---------- ModelStatus enum ----------


def test_model_status_enum_values():
    assert ModelStatus.TRAINING.value == "training"
    assert ModelStatus.READY.value == "ready"
    assert ModelStatus.DEPRECATED.value == "deprecated"
    assert ModelStatus.FAILED.value == "failed"
