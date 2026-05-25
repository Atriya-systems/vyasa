"""Vyasa training pipeline — turns SME-approved records into fine-tuning datasets.

Modules:
- data_prep: load approved JSONL exports → stratified train/eval splits in
  model-ready format. Filters at the legal gate (sme_verified + train_allowed
  only). Stratifies by subject + chapter + record_type.
- chat_templates: per-model chat-template formatting (Qwen3, Llama, Phi).
- golden_set: versioned eval-set tooling. Senior-teacher-authored
  query/ideal-response pairs, hash-pinned for reproducible eval runs.
- eval_harness: run any model against the golden set, score across 4
  dimensions, emit structured report.
- model_registry: versioned ledger of trained models with SHA-256 of weights,
  training config, dataset hash, eval scores, GPU/time/cost provenance.

The training pipeline is purely additive over Phase 1 — it consumes the
artefacts Phase 1 produces (approved JSONL exports) and produces trained
model adapters as outputs. No coupling to the content generation pipeline.

See `docs/PHASE_3_TRAINING_GUIDE.md` for the operator runbook.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
