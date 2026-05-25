from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA SFT training over conversational messages JSONL.")
    parser.add_argument("--model-name-or-path", required=True)
    parser.add_argument("--train-jsonl", required=True)
    parser.add_argument("--eval-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    args = parser.parse_args()

    try:
        from datasets import load_dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig
        from trl import SFTTrainer
    except Exception as exc:
        raise RuntimeError("Install requirements-training.txt before running training scripts.") from exc

    dataset = load_dataset("json", data_files={"train": args.train_jsonl, "eval": args.eval_jsonl})
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path, trust_remote_code=True, device_map="auto")

    peft_config = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM")
    train_args = TrainingArguments(
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=8,
        logging_steps=10,
        save_steps=50,
        eval_strategy="steps",
        eval_steps=50,
    )
    trainer = SFTTrainer(
        model=model,
        args=train_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        peft_config=peft_config,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(args.output_dir)


if __name__ == "__main__":
    main()
