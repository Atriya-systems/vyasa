"""Vyasa CLI — single entry point for the content + training pipelines.

Subcommands:
    Phase 1 — content generation:
        run             — batch generate one chapter end-to-end
        agent-run       — same as run, with LangGraph supervisor (retry + human gate)
        approve         — flip records to sme_verified + train_allowed
        export          — split SME-verified records into train/eval JSONL

    Phase 3 — training:
        train-data-prep — assemble SME-approved records into a training dataset
        register-model  — add a trained model to the registry
        list-models     — list registered models
        eval-model      — run a registered model against the golden set
        diff-evals      — compute delta between two eval reports
        golden-append   — add a golden eval record to the working set
        golden-freeze   — freeze the working set as a new version

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M3)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


# ---------- Phase 1 commands (carried from M1) ----------


def _run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True)
    parser.add_argument("--rights-ledger", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--chapter-no", required=True, type=int)
    parser.add_argument("--chapter-name", required=True)
    parser.add_argument("--limit-units", type=int, default=0)
    parser.add_argument("--llm-judge", action="store_true")


def cmd_run(args: argparse.Namespace) -> None:
    from aspireace_mocf.pipeline.runner import run_pipeline
    from aspireace_mocf.settings import load_settings
    settings = load_settings()
    result = run_pipeline(
        input_file=Path(args.input),
        rights_ledger_file=Path(args.rights_ledger),
        run_id=args.run_id,
        chapter_no=args.chapter_no,
        chapter_name=args.chapter_name,
        settings=settings,
        limit_units=args.limit_units,
        llm_judge=args.llm_judge,
    )
    print(json.dumps(result["outputs"], indent=2))


def cmd_agent_run(args: argparse.Namespace) -> None:
    from aspireace_mocf.agents.supervisor import run_agent
    from aspireace_mocf.settings import load_settings
    settings = load_settings()
    result = run_agent(
        input_file=Path(args.input),
        rights_ledger_file=Path(args.rights_ledger),
        run_id=args.run_id,
        chapter_no=args.chapter_no,
        chapter_name=args.chapter_name,
        settings=settings,
        limit_units=args.limit_units,
        llm_judge=args.llm_judge,
        human_in_loop=args.human_in_loop,
    )
    print(json.dumps(result, indent=2, default=str))


def cmd_approve(args: argparse.Namespace) -> None:
    from aspireace_mocf.pipeline.approve import approve_file
    result = approve_file(Path(args.input), Path(args.output), args.approver, args.reason)
    print(json.dumps(result, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    from aspireace_mocf.pipeline.export import export_app_content, export_training, write_export_summary
    from aspireace_mocf.pipeline.runner import APP_LANES
    from aspireace_mocf.settings import load_settings
    settings = load_settings()
    run_dir = Path("runs") / args.run_id
    exports = run_dir / "exports" / "training"
    exports.mkdir(parents=True, exist_ok=True)
    summary = {}
    if args.base:
        summary["base"] = export_training(
            Path(args.base), exports / "base_cpt_train.jsonl",
            exports / "base_cpt_eval.jsonl", settings, text_only=True,
        )
    if args.tutor:
        summary["tutor"] = export_training(
            Path(args.tutor), exports / "tutor_sft_train.jsonl",
            exports / "tutor_sft_eval.jsonl", settings,
        )
    if args.contentgen:
        summary["contentgen"] = export_training(
            Path(args.contentgen), exports / "contentgen_sft_train.jsonl",
            exports / "contentgen_sft_eval.jsonl", settings,
        )
    app_files = [run_dir / "verified" / f"{lane}_auto_checked.jsonl" for lane in APP_LANES]
    summary["app_content"] = export_app_content([p for p in app_files if p.exists()], run_dir / "exports" / "app_content")
    write_export_summary(run_dir / "exports" / "export_summary.json", summary)
    print(json.dumps(summary, indent=2))


# ---------- Phase 3 commands (added in M3) ----------


def cmd_train_data_prep(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.data_prep import (
        DataPrepConfig,
        discover_approved_jsonl,
        prepare_dataset,
    )
    runs = [Path(p) for p in args.runs_dir]
    sources = discover_approved_jsonl(runs)
    config = DataPrepConfig(
        dataset_id=args.dataset_id,
        target_model_name=args.target_model_name,
        max_seq_length=args.max_seq_length,
        eval_ratio=args.eval_ratio,
        random_seed=args.seed,
        artifacts_root=Path(args.artifacts_root),
    )
    manifest = prepare_dataset(sources=sources, config=config)
    print(json.dumps(manifest, indent=2, default=str))


def cmd_register_model(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.model_registry import (
        TrainingConfig,
        TrainingMetadata,
        register_model,
    )
    # Best-effort: if training_summary.json exists in the adapter dir, hydrate
    # the TrainingConfig + TrainingMetadata from it.
    summary_path = Path(args.adapter) / "training_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        cfg = summary.get("training_config", {})
        tc = TrainingConfig(
            base_model=args.base_model,
            method=summary.get("method", args.method),
            learning_rate=float(cfg.get("learning_rate", 2e-4)),
            max_steps=int(cfg.get("max_steps", 0)),
            per_device_train_batch_size=int(cfg.get("per_device_train_batch_size", 1)),
            gradient_accumulation_steps=int(cfg.get("gradient_accumulation_steps", 1)),
            lora_r=cfg.get("lora_r"),
            lora_alpha=cfg.get("lora_alpha"),
            lora_dropout=cfg.get("lora_dropout"),
        )
        tm: TrainingMetadata | None = None
        if "started_at_utc" in summary and "finished_at_utc" in summary:
            tm = TrainingMetadata(
                started_at_utc=summary["started_at_utc"],
                finished_at_utc=summary["finished_at_utc"],
                gpu_type=args.gpu_type,
                gpu_count=args.gpu_count,
                total_train_steps=int(cfg.get("max_steps", 0)),
                final_train_loss=summary.get("final_train_loss"),
                final_eval_loss=summary.get("final_eval_loss"),
                estimated_total_tokens=None,
                estimated_compute_cost_inr=args.compute_cost_inr,
            )
    else:
        # Manual mode — caller fills in just the essentials.
        tc = TrainingConfig(
            base_model=args.base_model,
            method=args.method,
            learning_rate=2e-4,
            max_steps=0,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
        )
        tm = None

    manifest = register_model(
        model_id=args.model_id,
        base_model=args.base_model,
        method=args.method,
        training_config=tc,
        artifact_path=Path(args.adapter),
        dataset_id=args.dataset_id,
        dataset_sha256=args.dataset_sha256,
        training_metadata=tm,
        status=args.status,
        notes=args.notes,
    )
    print(json.dumps(manifest, indent=2, default=str))


def cmd_list_models(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.model_registry import list_models
    rows = list_models(status=args.status)
    print(json.dumps(rows, indent=2, default=str))


def cmd_eval_model(args: argparse.Namespace) -> None:
    """Eval a registered model against a golden set version.

    Requires either --target-via-env (use PROVIDER from .env to talk to a
    served model) or --target-base-url (override).
    """
    from aspireace_mocf.providers.llm import LLMClient
    from aspireace_mocf.settings import Settings, load_settings
    from aspireace_mocf.training.eval_harness import run_eval
    from aspireace_mocf.training.model_registry import (
        get_model,
        update_model_eval,
    )

    settings = load_settings()
    target_model_meta = get_model(args.target_model)

    # Build target client. For most paths the target speaks OpenAI-compat via
    # LM Studio or vLLM. We reuse the Settings/.env mechanism by overriding
    # only the model name + URL.
    target_settings = Settings(**{**vars(settings),
                                  "model_name": args.target_model_name_override or target_model_meta.get("base_model", settings.model_name),
                                  "lmstudio_base_url": args.target_base_url or settings.lmstudio_base_url})
    target_client = LLMClient(target_settings)

    def target(messages: list[dict]) -> str:
        # Use chat_json with no schema → falls back to text. We'd ideally
        # have a chat_text method; for now wrap with a permissive parser.
        # The simplest path: ask the model to just generate text.
        resp = target_client.client.chat.completions.create(
            model=target_settings.model_name,
            messages=[{"role": "system", "content": "You are an AspireACE NEET/JEE tutor."}] + messages,
            temperature=0.1,
            max_tokens=1024,
        )
        return resp.choices[0].message.content or ""

    # Judge: a strong cloud judge if configured, else fall back to the same
    # client (cheap evals).
    judge_client = LLMClient(settings)

    def judge_json(prompt: str) -> dict:
        return judge_client.chat_json(prompt, temperature=0.0, max_tokens=1500)

    report = run_eval(
        run_id=args.run_id,
        golden_set_version=args.golden_set_version,
        target_model_name=args.target_model,
        judge_model_name=settings.model_name,
        target=target,
        judge_json=judge_json,
    )

    # Write back to the model_registry.
    update_model_eval(
        args.target_model,
        eval_run_id=args.run_id,
        golden_set_version=args.golden_set_version,
        aggregate_scores=report.aggregate_scores,
    )
    print(f"\n[eval] aggregate: {json.dumps(report.aggregate_scores, indent=2)}")
    print(f"[eval] full report: eval/runs/{args.run_id}/EVAL_SUMMARY.md")


def cmd_diff_evals(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.eval_harness import diff_eval_runs
    delta = diff_eval_runs(Path(args.report_a), Path(args.report_b))
    print(json.dumps(delta, indent=2))


def cmd_golden_append(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.golden_set import append_record
    record = json.loads(Path(args.record_json).read_text(encoding="utf-8"))
    append_record(record=record)
    print(f"[golden] appended record_id={record.get('record_id')}")


def cmd_golden_freeze(args: argparse.Namespace) -> None:
    from aspireace_mocf.training.golden_set import freeze_version
    manifest = freeze_version(version=args.version, notes=args.notes)
    print(json.dumps(manifest, indent=2))


# ---------- main ----------


def main() -> None:
    parser = argparse.ArgumentParser("vyasa", description="Vyasa — AspireACE ModelOps + ContentOps Factory")
    sub = parser.add_subparsers(required=True, dest="cmd")

    # Phase 1 commands
    p = sub.add_parser("run", help="Run deterministic full pipeline (Phase 1).")
    _run_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("agent-run", help="Phase 1 pipeline with LangGraph supervisor.")
    _run_args(p)
    p.add_argument("--human-in-loop", action="store_true")
    p.set_defaults(func=cmd_agent_run)

    p = sub.add_parser("approve", help="Approve records after SME/legal/content review.")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("export", help="Export approved training/app content.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--base", default="")
    p.add_argument("--tutor", default="")
    p.add_argument("--contentgen", default="")
    p.set_defaults(func=cmd_export)

    # Phase 3 commands
    p = sub.add_parser("train-data-prep", help="Phase 3: assemble SME-approved records into a training dataset.")
    p.add_argument("--dataset-id", required=True, help="Unique ID for this dataset (e.g. phy_v1_20260601).")
    p.add_argument("--target-model-name", default="Qwen/Qwen3-8B")
    p.add_argument("--runs-dir", nargs="+", default=["runs"], help="One or more runs directories to scan.")
    p.add_argument("--artifacts-root", default="artifacts/training_data")
    p.add_argument("--max-seq-length", type=int, default=4096)
    p.add_argument("--eval-ratio", type=float, default=0.10)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_train_data_prep)

    p = sub.add_parser("register-model", help="Phase 3: register a trained model in the ledger.")
    p.add_argument("--model-id", required=True)
    p.add_argument("--base-model", required=True, help="e.g. Qwen/Qwen3-8B")
    p.add_argument("--method", required=True, help="lora_sft | lora_cpt | full_sft | ...")
    p.add_argument("--adapter", required=True, help="Path to the trained adapter dir.")
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--dataset-sha256", default="", help="SHA-256 of the training dataset manifest (for provenance lock).")
    p.add_argument("--gpu-type", default="unknown")
    p.add_argument("--gpu-count", type=int, default=1)
    p.add_argument("--compute-cost-inr", type=float, default=0.0)
    p.add_argument("--status", default="ready", choices=["training", "ready", "deprecated", "failed"])
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_register_model)

    p = sub.add_parser("list-models", help="Phase 3: list registered models.")
    p.add_argument("--status", default=None, choices=[None, "training", "ready", "deprecated", "failed"])
    p.set_defaults(func=cmd_list_models)

    p = sub.add_parser("eval-model", help="Phase 3: run a model against a golden set version.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--target-model", required=True, help="Registered model_id to evaluate.")
    p.add_argument("--target-model-name-override", default=None, help="Override the served model name (use when target is served via vLLM with a different ID).")
    p.add_argument("--target-base-url", default=None, help="OpenAI-compat base URL where the target is served.")
    p.add_argument("--golden-set-version", required=True, help="e.g. v1")
    p.set_defaults(func=cmd_eval_model)

    p = sub.add_parser("diff-evals", help="Phase 3: diff two eval reports.")
    p.add_argument("--report-a", required=True)
    p.add_argument("--report-b", required=True)
    p.set_defaults(func=cmd_diff_evals)

    p = sub.add_parser("golden-append", help="Phase 3: append a golden eval record from a JSON file.")
    p.add_argument("--record-json", required=True, help="Path to JSON file containing one golden record.")
    p.set_defaults(func=cmd_golden_append)

    p = sub.add_parser("golden-freeze", help="Phase 3: freeze the working golden set as a versioned release.")
    p.add_argument("--version", default=None, help="Explicit version name (default: auto next vN).")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_golden_freeze)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
