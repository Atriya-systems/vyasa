# Training scripts — runbook

The three scripts in this directory form the training pipeline:

```
data_prep (in src/aspireace_mocf/training/) → train_lora_sft.py OR train_base_cpt.py → merge_adapter.py → quantize_for_serving.py
```

Each step is independent. You can run them on the same machine or on different machines (e.g. data_prep on your dev box, training on a rented Runpod A10G, quantize on the dev box).

See [`../docs/PHASE_3_TRAINING_GUIDE.md`](../docs/PHASE_3_TRAINING_GUIDE.md) for the full operator runbook with GPU sizing math and cost estimates.

---

## Quick reference

### 1. Prepare training data

```bash
python -m aspireace_mocf.cli train-data-prep \
  --dataset-id phy_v1_$(date +%Y%m%d) \
  --target-model-name Qwen/Qwen2.5-3B-Instruct \
  --runs-dir runs/
```

Reads SME-approved JSONL from `runs/*/verified/<lane>_sme_verified.jsonl`. Writes train/eval splits + manifest to `artifacts/training_data/<dataset-id>/`.

### 2. Train LoRA SFT adapter (tutor / content-generator)

```bash
# Local 5060 8GB:
python training/train_lora_sft.py \
  --model-name-or-path Qwen/Qwen2.5-3B-Instruct \
  --train-jsonl artifacts/training_data/phy_v1/tutor_app_train.jsonl \
  --eval-jsonl  artifacts/training_data/phy_v1/tutor_app_eval.jsonl \
  --output-dir  artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --use-qlora --max-steps 500
```

### 2b. (Alternative) Train LoRA CPT adapter (base subject corpus)

```bash
python training/train_base_cpt.py \
  --model-name-or-path Qwen/Qwen2.5-3B \
  --train-jsonl artifacts/training_data/phy_v1/base_subject_train.jsonl \
  --eval-jsonl  artifacts/training_data/phy_v1/base_subject_eval.jsonl \
  --output-dir  artifacts/adapters/base_qwen25-3b_phy_v1 \
  --use-qlora --max-steps 1000
```

### 3. Merge adapter into base for deployment

```bash
python training/merge_adapter.py \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --adapter   artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --output-dir artifacts/merged/tutor_qwen25-3b_phy_v1_merged
```

### 4. Quantize for serving on 5060 8GB

```bash
# For LM Studio (GGUF q4_k_m):
python training/quantize_for_serving.py \
  --merged-model artifacts/merged/tutor_qwen25-3b_phy_v1_merged \
  --output       artifacts/quantized/tutor_qwen25-3b_phy_v1.q4_k_m.gguf \
  --quant-method gguf-q4_k_m

# For vLLM (AWQ int4):
python training/quantize_for_serving.py \
  --merged-model artifacts/merged/tutor_qwen25-3b_phy_v1_merged \
  --output       artifacts/quantized/tutor_qwen25-3b_phy_v1_awq \
  --quant-method awq-int4 \
  --calibration-data artifacts/training_data/phy_v1/tutor_app_eval.jsonl
```

### 5. Register the trained model

```bash
python -m aspireace_mocf.cli register-model \
  --model-id tutor_qwen25-3b_phy_v1 \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --method lora_sft \
  --adapter artifacts/adapters/tutor_qwen25-3b_phy_v1 \
  --dataset-id phy_v1_20260601
```

### 6. Eval against the golden set

```bash
python -m aspireace_mocf.cli eval-model \
  --target-model tutor_qwen25-3b_phy_v1 \
  --golden-set-version v1
```

---

## GPU sizing — what fits where

| Hardware | VRAM | What it can train | What it can serve |
|---|---:|---|---|
| 5060 8GB | 8 GB | QLoRA on 3-4B (Qwen2.5-3B, Phi-3.5-mini) | int4-quantized 7-8B models via LM Studio |
| 4060/4070 16GB | 16 GB | QLoRA on 7-8B (Qwen3-8B) | bf16 7-8B; int4-quantized 14B |
| 3090/4090 24GB | 24 GB | Full LoRA on 8B, QLoRA on 14B | bf16 14B; int4-quantized 30B |
| A10G (Runpod) 24GB | 24 GB | Same as 3090/4090 | Same as 3090/4090 |
| A100 40GB | 40 GB | Full LoRA on 14B, QLoRA on 32B | bf16 32B |
| A100 80GB | 80 GB | Full LoRA on 32B, QLoRA on 70B | bf16 70B |

---

## Rough cost math (cloud rentals)

- Runpod A10G: ~₹150-200/hr. A typical 4-6h LoRA pass on Qwen3-8B = ₹600-1,200 per training run.
- Lambda A10: similar.
- Together AI / Fireworks: serverless fine-tuning, often $5-15 per million tokens — for 1.5M tokens of training data, ~₹400-1,200.

Recommended cadence: develop locally (free), train weekly/monthly on rented cloud (₹1-2K/run), iterate via the eval harness.

---

## Troubleshooting

**OOM on the 5060 8GB:**
Use `--use-qlora` + smaller model (Qwen2.5-3B / Phi-3.5-mini) + `--per-device-train-batch-size 1` + `--gradient-accumulation-steps 16`. If still OOM, rent an A10G.

**`bitsandbytes` import error:**
`pip install bitsandbytes`. On Windows, you need a CUDA-compatible build; consider running training in WSL2.

**Training loss not decreasing:**
Could mean wrong chat template, too-low learning rate, or LR too high. Eval the base model first to set a baseline, then check the training_summary.json's final_train_loss against it. Use MLflow to inspect the loss curve over time.

**vLLM not serving the AWQ-quantized model:**
Pass `--quantization awq` explicitly. Ensure the GPU has enough memory: an int4 8B model needs ~5GB VRAM + KV cache budget. With 8GB VRAM you can do batch size 1 with ~2K context.

**llama.cpp `convert` script not found:**
Install from https://github.com/ggerganov/llama.cpp; add `tools/` to PATH or copy `convert.py` + `quantize` binary to a directory on PATH.
