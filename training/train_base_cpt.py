#!/usr/bin/env python
"""LoRA continued-pretraining over base subject text JSONL.

Trains a LoRA adapter on plain ``{"text": "..."}`` JSONL records — the
base_subject lane of Vyasa. This is *not* instruction tuning; it teaches the
model raw subject-matter content (physics laws, chem reactions, bio
mechanisms) before behavior-tuning happens via SFT.

Typical usage:

    python training/train_base_cpt.py \
      --model-name-or-path Qwen/Qwen2.5-3B \
      --train-jsonl artifacts/training_data/v1/base_subject_train.jsonl \
      --eval-jsonl  artifacts/training_data/v1/base_subject_eval.jsonl \
      --output-dir  artifacts/adapters/base_qwen25-3b_v1 \
      --use-qlora --max-steps 1000

GPU sizing notes apply same as train_lora_sft.py. Base CPT generally needs
more steps than instruction-SFT to move the model meaningfully on plain text.

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
    for name, path in [("train-jsonl", args.train_jsonl), ("eval-jsonl", args.eval_jsonl)]:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"--{name} not found: {path!r}. "
                f"Run data_prep first to produce it."
            )
    if args.max_steps <= 0:
        raise ValueError(f"--max-steps must be > 0, got {args.max_steps}")
    if args.learning_rate <= 0:
        raise ValueError(f"--learning-rate must be > 0, got {args.learning_rate}")
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()) and not args.overwrite_output:
        raise FileExistsError(
            f"--output-dir {args.output_dir!r} exists and is non-empty. "
            f"Pass --overwrite-output to clobber."
        )


def _print_gpu_state() -> None:
    try:
        import torch
        if not torch.cuda.is_available():
            print("[gpu] no CUDA device available; will run on CPU.")
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LoRA CPT-style training over base subject text JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model-name-or-path", required=True)
    parser.add_argument("--train-jsonl", required=True)
    parser.add_argument("--eval-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--use-qlora", action="store_true")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mlflow-experiment", default=os.environ.get("MLFLOW_EXPERIMENT", "vyasa-base-cpt"))
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
            "Training deps missing. Install: pip install -r requirements-training.txt"
        ) from exc

    mlflow = None
    try:
        import mlflow as _mlflow
        _mlflow.set_tracking_uri(args.mlflow_tracking_uri)
        _mlflow.set_experiment(args.mlflow_experiment)
        mlflow = _mlflow
    except ImportError:
        print("[mlflow] not installed; skipping experiment tracking.")

    dataset = load_dataset(
        "json",
        data_files={"train": args.train_jsonl, "eval": args.eval_jsonl},
    )

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
        dataset_text_field="text",  # base CPT uses "text" key directly
    )

    if mlflow is not None:
        with mlflow.start_run(run_name=Path(args.output_dir).name):
            mlflow.log_params({
                "model_name_or_path": args.model_name_or_path,
                "max_steps": args.max_steps,
                "learning_rate": args.learning_rate,
                "method": "lora_cpt",
                "use_qlora": args.use_qlora,
                "lora_r": args.lora_r,
                "lora_alpha": args.lora_alpha,
            })
            trainer.train()
            trainer.save_model(args.output_dir)
    else:
        trainer.train()
        trainer.save_model(args.output_dir)

    finished_at = _now()
    summary = {
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "model_name_or_path": args.model_name_or_path,
        "method": "lora_cpt_qlora" if args.use_qlora else "lora_cpt",
        "training_config": {
            "max_steps": args.max_steps,
            "learning_rate": args.learning_rate,
            "use_qlora": args.use_qlora,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
            "max_seq_length": args.max_seq_length,
            "seed": args.seed,
        },
        "data": {
            "train_jsonl": str(Path(args.train_jsonl).resolve()),
            "eval_jsonl": str(Path(args.eval_jsonl).resolve()),
        },
        "output_dir": str(Path(args.output_dir).resolve()),
    }
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.output_dir) / "training_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(f"\n[done] training_summary.json written.")


if __name__ == "__main__":
    main()
