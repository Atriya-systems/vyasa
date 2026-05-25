from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge PEFT LoRA adapter into base model.")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except Exception as exc:
        raise RuntimeError("Install requirements-training.txt before running merge_adapter.") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(args.base_model, trust_remote_code=True, device_map="auto")
    model = PeftModel.from_pretrained(base, args.adapter)
    merged = model.merge_and_unload()
    merged.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
