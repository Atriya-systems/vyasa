from __future__ import annotations

import argparse
import json
from pathlib import Path

from aspireace_mocf.agents.supervisor import run_agent
from aspireace_mocf.pipeline.approve import approve_file
from aspireace_mocf.pipeline.export import export_app_content, export_training, write_export_summary
from aspireace_mocf.pipeline.runner import APP_LANES, run_pipeline
from aspireace_mocf.settings import load_settings


def _run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True)
    parser.add_argument("--rights-ledger", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--chapter-no", required=True, type=int)
    parser.add_argument("--chapter-name", required=True)
    parser.add_argument("--limit-units", type=int, default=0)
    parser.add_argument("--llm-judge", action="store_true")


def cmd_run(args: argparse.Namespace) -> None:
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
    result = approve_file(Path(args.input), Path(args.output), args.approver, args.reason)
    print(json.dumps(result, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    settings = load_settings()
    run_dir = Path("runs") / args.run_id
    exports = run_dir / "exports" / "training"
    exports.mkdir(parents=True, exist_ok=True)

    summary = {}
    if args.base:
        summary["base"] = export_training(Path(args.base), exports / "base_cpt_train.jsonl", exports / "base_cpt_eval.jsonl", settings, text_only=True)
    if args.tutor:
        summary["tutor"] = export_training(Path(args.tutor), exports / "tutor_sft_train.jsonl", exports / "tutor_sft_eval.jsonl", settings)
    if args.contentgen:
        summary["contentgen"] = export_training(Path(args.contentgen), exports / "contentgen_sft_train.jsonl", exports / "contentgen_sft_eval.jsonl", settings)

    app_files = [run_dir / "verified" / f"{lane}_auto_checked.jsonl" for lane in APP_LANES]
    summary["app_content"] = export_app_content([p for p in app_files if p.exists()], run_dir / "exports" / "app_content")
    write_export_summary(run_dir / "exports" / "export_summary.json", summary)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser("aspireace-mocf")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("run", help="Run deterministic full pipeline.")
    _run_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("agent-run", help="Run full pipeline with LangGraph supervisor.")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
