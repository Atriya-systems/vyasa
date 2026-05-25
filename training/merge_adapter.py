#!/usr/bin/env python
"""Merge a trained LoRA adapter into the base model and save as a standalone artifact.

Why merge: deployment is simpler with a single merged model than base+adapter
at runtime. Tradeoff: merged model is the same size as the base; you lose
the ability to swap adapters cheaply.

Typical usage:

    python training/merge_adapter.py \
      --base-model Qwen/Qwen3-8B \
      --adapter   artifacts/adapters/tutor_qwen3-8b_v1 \
      --output-dir artifacts/merged/tutor_qwen3-8b_v1_merged

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _validate_args(args: argparse.Namespace) -> None:
    if not Path(args.adapter).exists():
        raise FileNotFoundError(f"--adapter not found: {args.adapter}")
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()) and not args.overwrite_output:
        raise FileExistsError(
            f"--output-dir {args.output_dir!r} exists and is non-empty. "
            f"Pass --overwrite-output to clobber."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge PEFT LoRA adapter into base model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-model", required=True,
                        help="HuggingFace model id of the base, e.g. Qwen/Qwen3-8B.")
    parser.add_argument("--adapter", required=True,
                        help="Local path to the trained LoRA adapter directory.")
    parser.add_argument("--output-dir", required=True,
                        help="Where the merged model will be saved.")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--torch-dtype", default="bfloat16",
                        choices=["bfloat16", "float16", "float32"],
                        help="Dtype for the merged model. bf16 = best perf/size.")
    args = parser.parse_args()

    _validate_args(args)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except Exception as exc:
        raise RuntimeError(
            "Required deps missing. Install: pip install -r requirements-training.txt"
        ) from exc

    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }

    print(f"[merge] loading base model {args.base_model!r} in {args.torch_dtype}...")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        device_map="auto",
        torch_dtype=dtype_map[args.torch_dtype],
    )

    print(f"[merge] loading adapter {args.adapter!r}...")
    model = PeftModel.from_pretrained(base, args.adapter)

    print("[merge] merging adapter into base...")
    merged = model.merge_and_unload()

    print(f"[merge] saving merged model to {args.output_dir!r}...")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    print("[merge] done.")
    print("[next] Quantize for serving:")
    print(f"       python training/quantize_for_serving.py --merged-model {args.output_dir} ...")


if __name__ == "__main__":
    main()
