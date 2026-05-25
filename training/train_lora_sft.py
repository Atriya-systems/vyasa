#!/usr/bin/env python
"""LoRA SFT training for AspireACE tutor / content-generator models.

Trains a parameter-efficient LoRA adapter on top of a base causal-LM, using
conversational SFT data prepared by `src/aspireace_mocf/training/data_prep.py`.

Typical usage:

    # Local 5060 8GB — small model + QLoRA recommended
    python training/train_lora_sft.py \
      --model-name-or-path Qwen/Qwen2.5-3B-Instruct \
      --train-jsonl artifacts/training_data/v1/tutor_app_train.jsonl \
      --eval-jsonl  artifacts/training_data/v1/tutor_app_eval.jsonl \
      --output-dir  artifacts/adapters/tutor_qwen25-3b_v1 \
      --use-qlora --max-steps 500

    # Rented A10G / A100 — full LoRA on 8B+ model
    python training/train_lora_sft.py \
      --model-name-or-path Qwen/Qwen3-8B \
      --train-jsonl artifacts/training_data/v1/tutor_app_train.jsonl \
      --eval-jsonl  artifacts/training_data/v1/tutor_app_eval.jsonl \
      --output-dir  artifacts/adapters/tutor_qwen3-8b_v1 \
      --max-steps 1000 --learning-rate 1e-4

GPU sizing (rough):
  - 5060 8GB         → QLoRA only; Qwen2.5-3B or Phi-3.5-mini; batch=1
  - 3090/4090 24GB   → LoRA on 7-8B comfortably; batch=2-4
  - A10G 24GB        → same as 3090
  - A100 40GB / 80GB → full LoRA on 8-14B; batch=4-8

See `docs/PHASE_3_TRAINING_GUIDE.md` for the operator runbook.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _validate_args(args: argparse.Namespace) -> None:
    """Per-arg sanity checks. Fail early with actionable errors."""
    for name, path in [("train-jsonl", args.train_jsonl), ("eval-jsonl", args.eval_jsonl)]:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"--{name} not found: {path!r}. "
                f"Run `python -m aspireace_mocf.cli train-data-prep` first to produce it."
            )
    if args.max_steps <= 0:
        raise ValueError(f"--max-steps must be > 0, got {args.max_steps}")
    if args.learning_rate <= 0:
        raise ValueError(f"--learning-rate must be > 0, got {args.learning_rate}")
    if args.per_device_train_batch_size <= 0:
        raise ValueError(f"--per-device-train-batch-size must be > 0")
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()) and not args.overwrite_output:
        raise FileExistsError(
            f"--output-dir {args.output_dir!r} exists and is non-empty. "
            f"Pass --overwrite-output to clobber, or pick a different dir."
        )


def _print_gpu_state() -> None:
    """Print GPU memory state to stderr for the operator's benefit.

    Best-effort — silent if torch unavailable or no CUDA device."""
    try:
        import torch
        if not torch.cuda.is_available():
            print("[gpu] no CUDA device available; will run on CPU (very slow).")
            return
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            free_b, total_b = torch.cuda.mem_get_info(i)
            print(
                f"[gpu] device={i} name={props.name!r} "
                f"total_mem_gb={total_b/1e9:.1f} free_mem_gb={free_b/1e9:.1f}"
            )
    except Exception as exc:
        print(f"[gpu] state-probe failed: {exc}")


def _write_run_summary(output_dir: Path, summary: dict) -> None:
    """Write a structured summary that the model_registry can consume."""
    summary_path = output_dir / "training_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LoRA SFT training over conversational messages JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-name-or-path", required=True,
                        help="HuggingFace model id (e.g. Qwen/Qwen3-8B) OR local path.")
    parser.add_argument("--train-jsonl", required=True,
                        help="Path to train JSONL produced by data_prep.")
    parser.add_argument("--eval-jsonl", required=True,
                        help="Path to eval JSONL produced by data_prep.")
    parser.add_argument("--output-dir", required=True,
                        help="Where the LoRA adapter weights will land.")
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--use-qlora", action="store_true",
                        help="Use 4-bit base model loading (BitsAndBytes). Required for 5060 8GB.")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mlflow-experiment", default=os.environ.get("MLFLOW_EXPERIMENT", "vyasa-tutor-sft"))
    parser.add_argument("--mlflow-tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "mlruns"))
    args = parser.parse_args()

    _validate_args(args)
    _print_gpu_state()
    started_at = _now()

    try:
        from datasets import load_dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig, prepare_model_for_kbit_training
        from trl import SFTTrainer
        import torch
    except Exception as exc:
        raise RuntimeError(
            "Training deps missing. Install with: "
            "pip install -r requirements-training.txt"
        ) from exc

    # MLflow — optional but wired by default. Falls back gracefully if unavailable.
    mlflow = None
    try:
        import mlflow as _mlflow
        _mlflow.set_tracking_uri(args.mlflow_tracking_uri)
        _mlflow.set_experiment(args.mlflow_experiment)
        mlflow = _mlflow
    except ImportError:
        print("[mlflow] not installed; skipping experiment tracking.")
    except Exception as exc:
        print(f"[mlflow] tracking setup failed (continuing without): {exc}")

    # Data
    dataset = load_dataset(
        "json",
        data_files={"train": args.train_jsonl, "eval": args.eval_jsonl},
    )

    # Tokenizer + model
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict = {"trust_remote_code": True, "device_map": "auto"}
    if args.use_qlora:
        try:
            from transformers import BitsAndBytesConfig
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        except ImportError as exc:
            raise RuntimeError(
                "QLoRA requires bitsandbytes. Install: pip install bitsandbytes"
            ) from exc

    model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path, **model_kwargs)
    if args.use_qlora:
        model = prepare_model_for_kbit_training(model)

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    train_args = TrainingArguments(
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        logging_steps=10,
        save_steps=50,
        eval_strategy="steps",
        eval_steps=50,
        seed=args.seed,
        gradient_checkpointing=True,
        bf16=True,
        report_to=["mlflow"] if mlflow is not None else [],
    )

    trainer = SFTTrainer(
        model=model,
        args=train_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        peft_config=peft_config,
        processing_class=tokenizer,
    )

    if mlflow is not None:
        with mlflow.start_run(run_name=Path(args.output_dir).name) as run:
            mlflow.log_params({
                "model_name_or_path": args.model_name_or_path,
                "max_steps": args.max_steps,
                "learning_rate": args.learning_rate,
                "per_device_train_batch_size": args.per_device_train_batch_size,
                "gradient_accumulation_steps": args.gradient_accumulation_steps,
                "lora_r": args.lora_r,
                "lora_alpha": args.lora_alpha,
                "lora_dropout": args.lora_dropout,
                "use_qlora": args.use_qlora,
                "seed": args.seed,
            })
            trainer.train()
            trainer.save_model(args.output_dir)
    else:
        trainer.train()
        trainer.save_model(args.output_dir)

    finished_at = _now()
    # Summary the model_registry can pick up.
    summary = {
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "model_name_or_path": args.model_name_or_path,
        "method": "lora_sft_qlora" if args.use_qlora else "lora_sft",
        "training_config": {
            "max_steps": args.max_steps,
            "learning_rate": args.learning_rate,
            "per_device_train_batch_size": args.per_device_train_batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
            "use_qlora": args.use_qlora,
            "max_seq_length": args.max_seq_length,
            "seed": args.seed,
        },
        "data": {
            "train_jsonl": str(Path(args.train_jsonl).resolve()),
            "eval_jsonl": str(Path(args.eval_jsonl).resolve()),
        },
        "output_dir": str(Path(args.output_dir).resolve()),
        "final_train_loss": getattr(trainer.state, "log_history", [{}])[-1].get("loss") if hasattr(trainer, "state") else None,
    }
    _write_run_summary(Path(args.output_dir), summary)
    print(f"\n[done] training_summary.json written to {args.output_dir}/training_summary.json")
    print("[next] register the adapter with the model registry:")
    print(f"       python -m aspireace_mocf.cli register-model --adapter {args.output_dir} ...")


if __name__ == "__main__":
    main()
