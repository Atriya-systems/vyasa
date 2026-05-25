# Vyasa — AspireACE ModelOps + ContentOps Factory

> *Vyasa (व्यास)* — the legendary sage who compiled the Vedas and the Mahabharata. This factory does the same job for AspireACE: it compiles raw SME source material into structured, governed, ready-to-ship content + training data.

A production-oriented dataset and content factory for the AspireACE NEET/JEE app, owned and operated by Atriya Systems.

**Codename:** Vyasa
**Version:** v1.0.0-M1 (Foundation + Phase 1 hardened — see [CHANGELOG.md](CHANGELOG.md))
**Repository:** https://github.com/Atriya-systems/vyasa
**Status:** Phase 1 production-ready. See [HANDOFF.md](HANDOFF.md) for current state, [PHASE_ROADMAP.md](PHASE_ROADMAP.md) for what comes next.

---

## What it does

It creates and governs **three model-training lanes** plus **app-operational content lanes**:

```text
Owned/reference-guided source
→ rights validation
→ source units
→ base subject corpus
→ tutor/app SFT
→ content-generator SFT
→ notes/tricks/misconceptions/DPP/revision/rubric app content
→ RAG chunks
→ offline bundles
→ review/approval gates
→ training exports
→ app binding maps
→ manifests + MLflow/DVC-ready tracking
```

## Why v3 exists

v2 was model-data oriented. v3 is AspireACE-app oriented.

AspireACE needs:

- base subject knowledge for model adaptation
- student-facing tutor behavior
- internal content-generator behavior
- app-ready notes/tricks/revision/DPP/rubric content
- RAG chunks for grounded answers
- offline bundles for low-connectivity deployment
- rights ledger and approval gating
- review UI + human-in-loop queues
- engine/surface binding to AspireOS/AspireACE runtime

## Legal / provenance design

This repo assumes API models are used as:

```text
draft generator
cleaner
reviewer
judge
rewriter assistant
```

API-drafted records are **not automatically trainable**.

Every record starts as:

```json
"train_allowed": false
```

Records become trainable only after rights + quality approval:

```json
"quality_status": "sme_verified",
"train_allowed": true
```

## Output groups

```text
runs/<run_id>/
├── source_units/source_units.jsonl
├── lanes/base_subject.jsonl
├── lanes/tutor_app.jsonl
├── lanes/content_generator.jsonl
├── lanes/notes.jsonl
├── lanes/tricks.jsonl
├── lanes/misconceptions.jsonl
├── lanes/dpp_tests.jsonl
├── lanes/grading_feedback.jsonl
├── lanes/revision.jsonl
├── rag/chunks.jsonl
├── offline/chapter_bundle.json
├── verified/*.jsonl
├── queues/*.jsonl
├── exports/training/*.jsonl
├── exports/app_content/*.jsonl
├── exports/rag/*.jsonl
├── exports/offline/*.json
├── manifests/run_manifest.json
└── reports/*.json
```

## Install

```bash
cd aspireace_modelops_contentops_factory_v3
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Mac/Linux:

```bash
source .venv/bin/activate
```

Core install:

```bash
pip install -r requirements-core.txt
```

Optional training install:

```bash
pip install -r requirements-training.txt
```

Optional review app install:

```bash
pip install -r requirements-review.txt
```

## Configure

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### LM Studio

```env
PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_API_KEY=lm-studio
MODEL_NAME=qwen/qwen3
```

### OpenAI-compatible API

```env
PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-5.5
```

## Run sample

```bash
python -m aspireace_mocf.cli run \
  --input examples/sample_owned_source.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id sample_v3 \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 3
```

## Run with LLM judge

```bash
python -m aspireace_mocf.cli run \
  --input examples/sample_owned_source.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id sample_v3_judge \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 3 \
  --llm-judge
```

## Run with LangGraph supervisor

```bash
python -m aspireace_mocf.cli agent-run \
  --input examples/sample_owned_source.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id sample_v3_agent \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 3 \
  --llm-judge \
  --human-in-loop
```

## Start review app

```bash
streamlit run review_app/app.py -- --run-dir runs/sample_v3
```

## Approve records after review

```bash
python -m aspireace_mocf.cli approve \
  --input runs/sample_v3/verified/base_subject_auto_checked.jsonl \
  --output runs/sample_v3/verified/base_subject_sme_verified.jsonl \
  --approver "physics_sme_001" \
  --reason "SME verified source-grounded original content"
```

## Export train/eval

```bash
python -m aspireace_mocf.cli export \
  --run-id sample_v3 \
  --base runs/sample_v3/verified/base_subject_sme_verified.jsonl \
  --tutor runs/sample_v3/verified/tutor_app_sme_verified.jsonl \
  --contentgen runs/sample_v3/verified/content_generator_sme_verified.jsonl
```

## Train later

Base corpus uses standard `{"text": "..."}` JSONL.

Tutor/content-generator use conversational `{"messages": [...]}` JSONL.

```bash
python training/train_base_cpt.py \
  --model-name-or-path Qwen/Qwen3-8B \
  --train-jsonl runs/sample_v3/exports/training/base_cpt_train.jsonl \
  --eval-jsonl runs/sample_v3/exports/training/base_cpt_eval.jsonl \
  --output-dir artifacts/base_cpt_lora
```

```bash
python training/train_lora_sft.py \
  --model-name-or-path Qwen/Qwen3-8B \
  --train-jsonl runs/sample_v3/exports/training/tutor_sft_train.jsonl \
  --eval-jsonl runs/sample_v3/exports/training/tutor_sft_eval.jsonl \
  --output-dir artifacts/tutor_lora
```

## Safety rules

Never train on:

```text
runs/<run_id>/lanes/*.jsonl
runs/<run_id>/verified/*_auto_checked.jsonl
```

Train only on approved exports:

```text
runs/<run_id>/exports/training/*.jsonl
```

## AspireACE runtime binding

Static binding files live in:

```text
app_binding/
├── aspireace_surface_map.json
├── engine_binding_map.json
├── feature_flag_seed.json
└── runtime_routes.json
```

The pipeline also writes run-specific copies into:

```text
runs/<run_id>/exports/manifests/
```
