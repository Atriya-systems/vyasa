# Phase 3 — Training Guide

**Audience:** the operator (you or a future agent) actually running the fine-tuning pipeline.

**Prerequisites:**
- M1 Phase 1 content factory is operational and has produced ≥ a few hundred SME-approved records.
- A senior-teacher-authored golden eval set exists (or is being authored).
- A GPU available — local (5060 8GB minimum) or rented (Runpod / Lambda Labs).

For why training is sequenced where it is in the milestone plan, see [PHASE_ROADMAP.md](../PHASE_ROADMAP.md) §M3.

---

## The training pipeline at a glance

```
[approved JSONL]
     |
     v
[train-data-prep]  →  [train_lora_sft / train_base_cpt]  →  [merge_adapter]  →  [quantize_for_serving]  →  [register-model]  →  [eval-model]
     |                       |                                    |                       |                        |                       |
     v                       v                                    v                       v                        v                       v
  artifacts/         artifacts/adapters/                    artifacts/             artifacts/             artifacts/                eval/runs/
  training_data/     <adapter>/                             merged/                quantized/             model_registry/           <run_id>/
```

Six steps. Each one independent. You can run them on the same machine or split across machines (data_prep on dev, training on rented GPU, quantize on dev, register on dev).

---

## Step 1 — Prepare the training dataset

Reads SME-approved JSONL from one or more `runs/<id>/verified/` directories. Applies the legal gate (`train_allowed=true` + `quality_status=sme_verified` + approver + timestamp + drafted_by). Stratifies by subject + chapter + record_type. Splits train/eval per `--eval-ratio`. Writes manifest with SHA-256 of source files.

```bash
python -m aspireace_mocf.cli train-data-prep \
  --dataset-id phy_v1_20260601 \
  --target-model-name Qwen/Qwen2.5-3B-Instruct \
  --runs-dir runs/ \
  --eval-ratio 0.10
```

Outputs:
- `artifacts/training_data/phy_v1_20260601/base_subject_train.jsonl`
- `artifacts/training_data/phy_v1_20260601/base_subject_eval.jsonl`
- `artifacts/training_data/phy_v1_20260601/tutor_app_train.jsonl`
- `artifacts/training_data/phy_v1_20260601/tutor_app_eval.jsonl`
- `artifacts/training_data/phy_v1_20260601/content_generator_train.jsonl`
- `artifacts/training_data/phy_v1_20260601/content_generator_eval.jsonl`
- `artifacts/training_data/phy_v1_20260601/manifest.json`
- `artifacts/training_data/phy_v1_20260601/filtered_out.jsonl` (audit trail of rejects)

**Inspect before training:**
- Check `manifest.json` → `total_train` + `total_eval`. Are the numbers reasonable?
- Check `filtered_out.jsonl` → why were records rejected? Common reasons: `not_sme_verified` (still in the queue), `exceeds_max_seq_length` (lower `--max-seq-length` or chunk the source).

---

## Step 2 — Train a LoRA SFT adapter

For tutor / content-generator lanes (conversational `messages`):

```bash
python training/train_lora_sft.py \
  --model-name-or-path Qwen/Qwen2.5-3B-Instruct \
  --train-jsonl artifacts/training_data/phy_v1_20260601/tutor_app_train.jsonl \
  --eval-jsonl  artifacts/training_data/phy_v1_20260601/tutor_app_eval.jsonl \
  --output-dir  artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --use-qlora \
  --max-steps 500 \
  --learning-rate 2e-4
```

For base_subject lane (plain text):

```bash
python training/train_base_cpt.py \
  --model-name-or-path Qwen/Qwen2.5-3B \
  --train-jsonl artifacts/training_data/phy_v1_20260601/base_subject_train.jsonl \
  --eval-jsonl  artifacts/training_data/phy_v1_20260601/base_subject_eval.jsonl \
  --output-dir  artifacts/adapters/base_qwen25-3b_phy_v1 \
  --use-qlora \
  --max-steps 1000
```

Outputs land in `--output-dir`, including a `training_summary.json` that `register-model` reads automatically.

---

## Step 3 — Merge adapter into the base model

The LoRA adapter is small (~50-100 MB), but for serving most stacks prefer a single merged model:

```bash
python training/merge_adapter.py \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --adapter   artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --output-dir artifacts/merged/tutor_qwen25-3b_phy_v1_merged \
  --torch-dtype bfloat16
```

---

## Step 4 — Quantize for serving

The merged model is the size of the base (~6GB for a 3B at bf16, ~16GB for an 8B). Quantize to int4 to serve on the 5060 8GB:

**GGUF for LM Studio:**
```bash
python training/quantize_for_serving.py \
  --merged-model artifacts/merged/tutor_qwen25-3b_phy_v1_merged \
  --output       artifacts/quantized/tutor_qwen25-3b_phy_v1.q4_k_m.gguf \
  --quant-method gguf-q4_k_m
```

**AWQ for vLLM:**
```bash
python training/quantize_for_serving.py \
  --merged-model artifacts/merged/tutor_qwen25-3b_phy_v1_merged \
  --output       artifacts/quantized/tutor_qwen25-3b_phy_v1_awq \
  --quant-method awq-int4 \
  --calibration-data artifacts/training_data/phy_v1_20260601/tutor_app_eval.jsonl
```

---

## Step 5 — Register the trained model

```bash
python -m aspireace_mocf.cli register-model \
  --model-id tutor_qwen25-3b_phy_v1 \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --method lora_sft \
  --adapter artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --dataset-id phy_v1_20260601 \
  --gpu-type RTX_5060_8GB \
  --gpu-count 1 \
  --status ready \
  --notes "first lora pass; physics only; qlora int4"
```

If `training_summary.json` exists in `--adapter`, hyperparameters + timestamps are hydrated automatically.

---

## Step 6 — Evaluate against the golden set

First load the trained quantized model in LM Studio (or vLLM), then:

```bash
python -m aspireace_mocf.cli eval-model \
  --run-id eval_tutor_v1_$(date +%s) \
  --target-model tutor_qwen25-3b_phy_v1 \
  --target-base-url http://localhost:1234/v1 \
  --target-model-name-override "tutor_qwen25-3b_phy_v1.q4_k_m" \
  --golden-set-version v1
```

This:
1. Loads the golden set v1 (verifies SHA-256).
2. For each golden record, queries the target model.
3. Calls the judge (default: same provider as your .env PROVIDER; recommend a strong cloud model like Claude Sonnet for trustworthy scoring).
4. Aggregates scores per-dimension, per-subject, per-difficulty.
5. Writes `eval/runs/<run_id>/eval_report.json` + `EVAL_SUMMARY.md` + `record_results.jsonl`.
6. Updates `artifacts/model_registry/tutor_qwen25-3b_phy_v1/eval_history.jsonl` with the new run + best score.

---

## Step 7 (optional) — Compare two model versions

```bash
python -m aspireace_mocf.cli diff-evals \
  --report-a eval/runs/eval_tutor_v0_baseline/eval_report.json \
  --report-b eval/runs/eval_tutor_v1/eval_report.json
```

Prints per-dimension + per-subject delta. **Refuses to give meaningful comparison if the two reports used different golden set versions** (will log a warning).

---

## Building the golden eval set

You need this BEFORE evaluating anything. Each golden record is a senior-teacher-authored query/ideal-response pair the model must answer well.

**Append a record:**

```bash
cat > /tmp/golden_001.json << 'EOF'
{
  "record_id": "GOLD_PHY11_CH01_001",
  "query": "Why is dimensional analysis useful in physics?",
  "ideal_response": "Dimensional analysis is useful because [senior-teacher-authored 200-word explanation goes here]...",
  "subject": "Physics",
  "chapter_no": 1,
  "chapter_name": "Units and Measurements",
  "topic": "Dimensional Analysis",
  "difficulty": "basic",
  "dimensions": {
    "subject_correctness": 5,
    "teaching_quality": 5,
    "source_grounding": 5,
    "app_usefulness": 5
  },
  "author_teacher_id": "teacher_ashwin"
}
EOF

python -m aspireace_mocf.cli golden-append --record-json /tmp/golden_001.json
```

**Freeze a working set as v1 once you have ~200 records:**

```bash
python -m aspireace_mocf.cli golden-freeze --notes "initial 200-record set; physics-only; authored by Ashwin (senior)"
```

This locks the set and computes SHA-256. From now on, eval runs reference `v1` for reproducibility.

**Add more records later:** just `golden-append` again; freeze as `v2` when ready.

---

## GPU sizing — what you can actually do where

See `../training/README.md` for the table. Short version:

| Hardware | Train Qwen3-8B QLoRA? | Train Qwen2.5-3B QLoRA? | Serve 8B int4? | Serve 3B int4? |
|---|---|---|---|---|
| **5060 8GB** | Tight (~8h, batch=1) | Comfortable | Yes (~5GB) | Yes (~2.5GB) |
| **4090 24GB** | Comfortable | Easy | Yes | Yes |
| **A10G 24GB (Runpod)** | Comfortable | Easy | Yes | Yes |
| **A100 40GB** | Full LoRA possible | Easy | Yes | Yes |

**Cloud-rental cost (rough):**
- 1 LoRA pass on Qwen3-8B (4-6 hrs on A10G): ~₹600-1,200
- 1 LoRA pass on Qwen2.5-3B (1-2 hrs on A10G): ~₹150-300
- 1 eval run against 200 golden records: ~$0.50-2 in judge LLM tokens (Claude/GPT)

---

## When to train vs when to wait

**Train when:**
- You have ≥ ~1,000 SME-approved records across the trainable lanes
- The golden eval set has ≥ 100 records covering at least 2 subjects
- Your prompt-chained baseline scores < 0.80 on the golden set (meaning there's headroom)
- A specific failure mode keeps appearing in SME review (e.g. "Qwen base keeps getting NEET-Bio process steps in wrong order") — training to fix it is worth it

**Wait when:**
- Approved records < ~500 — not enough signal; LoRA will overfit to noise
- Golden set < 50 records — can't measure improvement
- Prompt-chained baseline is already > 0.90 — diminishing returns
- No GPU + no budget for cloud rental — just sit on the data, train later

---

## Troubleshooting

**Training loss not decreasing:**
- Wrong chat template (model expects ChatML; data is plain text). Check `chat_templates.detect_template_from_model_name(...)`.
- LR too high (try 1e-4 or 5e-5).
- LoRA rank too small for the task complexity (try r=32 or r=64).

**Eval scores are noisy / inconsistent across runs:**
- Set temperature=0.0 in the target. Vyasa's `eval_model` does this; if you're calling judge separately, verify.
- Increase golden set size — 200 records is the minimum for stable means.
- Use the SAME judge across all eval runs you compare. Mixing Claude vs GPT vs Qwen judges gives meaningless deltas.

**OOM during training:**
- Smaller base model (Qwen2.5-3B instead of Qwen3-8B).
- `--use-qlora` flag (4-bit base via bitsandbytes).
- `--per-device-train-batch-size 1` + `--gradient-accumulation-steps 16+`.
- Rent a bigger GPU (Runpod A10G 24GB, ~₹150-200/hr).

**Trained model worse than base on golden set:**
- Overfitting — reduce `--max-steps` or increase `--eval-ratio`.
- Bad data — check the `filtered_out.jsonl`; if too much was rejected, the surviving set may be unrepresentative.
- Chat template mismatch — base model speaks ChatML, training data was formatted as Llama; check.

---

## What this guide does NOT cover

- **Phase 4 multi-tenant productization** — billing, rate limits, public API. See [PHASE_ROADMAP.md](../PHASE_ROADMAP.md) §M4 when relevant.
- **Distillation** — training a smaller student model on the bigger teacher. Premature until the teacher is proven valuable.
- **RLHF / DPO** — preference-tuning beyond SFT. Possible Phase 3.5; not in M3 scope.
- **Multi-modal training** (text + images) — pure text in M3. Image / diagram handling deferred.

---

*Update this guide when the training pipeline changes (new commands, new models supported, new quant methods, etc.). Not for every code edit.*
