#!/usr/bin/env python
"""Quantize a merged model for serving (int4 / int8 GGUF / AWQ / bnb).

Why: the merged FP16/BF16 model is too big to serve on the 5060 8GB (or any
small GPU). Quantizing to int4 cuts the memory footprint ~4× and lets the
trained model serve in the same LM Studio that Vyasa generates against.

Supported quantization paths:

  - bnb-int4 / bnb-int8: in-process bitsandbytes load, no separate artifact.
    Loads when you call AutoModelForCausalLM.from_pretrained(..., quantization_config=...).
    Useful for vLLM and transformers serving.

  - GGUF q4_k_m / q5_k_m / q8_0: external llama.cpp conversion. Best for
    LM Studio + Ollama. Produces a single .gguf file you can load directly.
    Requires llama.cpp's convert + quantize binaries on PATH.

Typical usage:

    # GGUF q4_k_m (for LM Studio on the 5060)
    python training/quantize_for_serving.py \
      --merged-model artifacts/merged/tutor_qwen3-8b_v1_merged \
      --output       artifacts/quantized/tutor_qwen3-8b_v1.q4_k_m.gguf \
      --quant-method gguf-q4_k_m

    # AWQ int4 (for vLLM)
    python training/quantize_for_serving.py \
      --merged-model artifacts/merged/tutor_qwen3-8b_v1_merged \
      --output       artifacts/quantized/tutor_qwen3-8b_v1_awq \
      --quant-method awq-int4 \
      --calibration-data artifacts/training_data/v1/tutor_app_eval.jsonl

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


QUANT_METHODS: tuple[str, ...] = (
    "gguf-q4_k_m",
    "gguf-q5_k_m",
    "gguf-q8_0",
    "awq-int4",
    "bnb-int4",
    "bnb-int8",
)


def _validate_args(args: argparse.Namespace) -> None:
    if not Path(args.merged_model).exists():
        raise FileNotFoundError(f"--merged-model not found: {args.merged_model}")
    if args.quant_method not in QUANT_METHODS:
        raise ValueError(
            f"--quant-method {args.quant_method!r} unknown. Allowed: {QUANT_METHODS}"
        )
    if args.quant_method.startswith("awq-") and not args.calibration_data:
        raise ValueError("AWQ quantization requires --calibration-data.")


def _quantize_gguf(merged_model: Path, output: Path, method: str) -> None:
    """GGUF quantization via llama.cpp. Requires llama.cpp/convert.py +
    quantize binary on PATH or in tools/. Best path for LM Studio."""
    # The exact tool path depends on the installer. We try common locations.
    convert_script = shutil.which("convert-hf-to-gguf.py") or shutil.which("convert.py")
    quantize_bin = shutil.which("llama-quantize") or shutil.which("quantize")

    if not convert_script or not quantize_bin:
        raise RuntimeError(
            "GGUF quantization requires llama.cpp's convert-hf-to-gguf.py + "
            "llama-quantize on PATH. Install: https://github.com/ggerganov/llama.cpp"
        )

    # Step 1: HF → unquantized GGUF (f16)
    f16_path = output.with_suffix(".f16.gguf")
    print(f"[quantize-gguf] step 1: HF -> f16 GGUF at {f16_path}")
    subprocess.run(
        [sys.executable, convert_script, str(merged_model), "--outfile", str(f16_path), "--outtype", "f16"],
        check=True,
    )

    # Step 2: f16 → target quantization
    q_type = method.split("-", 1)[1]  # e.g. "q4_k_m"
    print(f"[quantize-gguf] step 2: {f16_path} -> {q_type} at {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [quantize_bin, str(f16_path), str(output), q_type.upper()],
        check=True,
    )

    # Clean up the intermediate f16 file (large, no further use).
    if f16_path.exists() and not os.environ.get("VYASA_KEEP_F16_GGUF"):
        print(f"[quantize-gguf] removing intermediate {f16_path}")
        f16_path.unlink()

    print(f"[quantize-gguf] done. Output: {output}")
    print("[next] load this .gguf in LM Studio: drag into the Models tab.")


def _quantize_awq(merged_model: Path, output: Path, calibration_data: Path) -> None:
    """AWQ int4 quantization. Best for vLLM serving."""
    try:
        from awq import AutoAWQForCausalLM
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "AWQ quantization requires autoawq. Install: pip install autoawq"
        ) from exc

    print(f"[quantize-awq] loading model {merged_model}...")
    model = AutoAWQForCausalLM.from_pretrained(str(merged_model), trust_remote_code=True)
    tokenizer = AutoTokenizer.from_pretrained(str(merged_model), trust_remote_code=True)

    quant_config = {
        "zero_point": True,
        "q_group_size": 128,
        "w_bit": 4,
        "version": "GEMM",
    }
    print(f"[quantize-awq] quantizing with config {quant_config}...")
    model.quantize(tokenizer, quant_config=quant_config, calib_data=str(calibration_data))

    output.mkdir(parents=True, exist_ok=True)
    model.save_quantized(str(output))
    tokenizer.save_pretrained(str(output))
    print(f"[quantize-awq] done. Output: {output}")
    print("[next] serve with vLLM: vllm serve <output> --quantization awq")


def _quantize_bnb_info(method: str) -> None:
    """bnb int4/int8 doesn't produce a separate artifact — it's an in-process
    load setting. Just print guidance."""
    bit = method.split("-", 1)[1]
    print(f"[quantize-bnb] bnb-{bit} quantization is applied at LOAD TIME, not as a")
    print(f"               separate artifact. To serve the merged model in bnb-{bit}:")
    print()
    print("from transformers import AutoModelForCausalLM, BitsAndBytesConfig, AutoTokenizer")
    print("import torch")
    print()
    print(f"config = BitsAndBytesConfig(load_in_{bit}bit=True,")
    if bit == "int4":
        print("                            bnb_4bit_compute_dtype=torch.bfloat16,")
        print("                            bnb_4bit_quant_type='nf4',")
        print("                            bnb_4bit_use_double_quant=True)")
    print(f"model = AutoModelForCausalLM.from_pretrained('<MERGED_PATH>',")
    print("                                              quantization_config=config,")
    print("                                              device_map='auto')")
    print()
    print(f"No artifact written. Model loads in bnb-{bit} when you set quantization_config.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantize a merged model for serving on smaller GPUs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--merged-model", required=True,
                        help="Directory of the merged model (from merge_adapter.py).")
    parser.add_argument("--output", required=True,
                        help="Output path. For GGUF: a .gguf file. For AWQ: a directory.")
    parser.add_argument("--quant-method", required=True, choices=QUANT_METHODS,
                        help="Quantization method.")
    parser.add_argument("--calibration-data", default=None,
                        help="Required for AWQ. Path to a JSONL of calibration prompts "
                             "(e.g. an eval split from data_prep).")
    args = parser.parse_args()

    _validate_args(args)
    merged_model = Path(args.merged_model)
    output = Path(args.output)

    if args.quant_method.startswith("gguf-"):
        _quantize_gguf(merged_model, output, args.quant_method)
    elif args.quant_method.startswith("awq-"):
        _quantize_awq(merged_model, output, Path(args.calibration_data))
    elif args.quant_method.startswith("bnb-"):
        _quantize_bnb_info(args.quant_method)
    else:
        raise ValueError(f"Unknown quant method: {args.quant_method}")


if __name__ == "__main__":
    main()
