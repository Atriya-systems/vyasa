from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from aspireace_mocf.pipeline.approve import approve_file
from aspireace_mocf.pipeline.export import copy_json_file
from aspireace_mocf.pipeline.lane_generation import generate_app_lane, generate_training_lane
from aspireace_mocf.pipeline.manifest import write_manifest
from aspireace_mocf.pipeline.paths import RunPaths
from aspireace_mocf.pipeline.rag_offline import build_offline_bundle, build_rag_chunks
from aspireace_mocf.pipeline.source_units import build_source_units
from aspireace_mocf.pipeline.verify import verify_lane
from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.jsonio import write_json
from aspireace_mocf.utils.text import extract_source_id
from aspireace_mocf.utils.jsonio import read_json
from aspireace_mocf.validators.rights_validator import load_rights_ledger, validate_source_for_lane


TRAIN_LANES = ["base_subject", "tutor_app", "content_generator"]
APP_LANES = ["notes", "tricks", "misconceptions", "dpp_tests", "grading_feedback", "revision"]


def run_pipeline(
    *,
    input_file: Path,
    rights_ledger_file: Path,
    run_id: str,
    chapter_no: int,
    chapter_name: str,
    settings: Settings,
    limit_units: int = 0,
    llm_judge: bool = False,
) -> dict[str, Any]:
    paths = RunPaths.create(run_id)
    llm = LLMClient(settings)
    counts: dict[str, Any] = {}

    ledger = load_rights_ledger(rights_ledger_file)
    source_id = extract_source_id(read_json(input_file))
    rights_summary = {}
    for lane in ["base_subject", "tutor_app", "content_generator", "app_content", "rag", "offline"]:
        ok, reason = validate_source_for_lane(ledger, source_id, lane if lane != "app_content" else "app_content")
        rights_summary[lane] = {"ok": ok, "reason": reason}
    if not rights_summary["rag"]["ok"] and not rights_summary["app_content"]["ok"]:
        raise RuntimeError(f"Rights ledger blocks core non-training usage for source_id={source_id}: {rights_summary}")

    units_file = paths.source_units / "source_units.jsonl"
    counts["source_units"] = build_source_units(
        input_file=input_file,
        output_file=units_file,
        rejected_file=paths.source_units / "rejected_source_units.jsonl",
        chapter_no=chapter_no,
        chapter_name=chapter_name,
        settings=settings,
        llm=llm,
        limit_units=limit_units,
    )

    for lane in TRAIN_LANES:
        output_file = paths.lanes / f"{lane}.jsonl"
        rejected_file = paths.queues / f"rejected_generation_{lane}.jsonl"
        count = {
            "base_subject": settings.base_records_per_unit,
            "tutor_app": settings.tutor_records_per_unit,
            "content_generator": settings.contentgen_records_per_unit,
        }[lane]
        counts[lane] = generate_training_lane(
            units_file=units_file,
            output_file=output_file,
            rejected_file=rejected_file,
            lane=lane,
            count=count,
            settings=settings,
            llm=llm,
        )

    app_count_map = {
        "notes": settings.app_cards_per_unit,
        "tricks": settings.app_cards_per_unit,
        "misconceptions": settings.app_cards_per_unit,
        "dpp_tests": settings.dpp_records_per_unit,
        "grading_feedback": settings.rubric_records_per_unit,
        "revision": settings.revision_records_per_unit,
    }
    app_card_files = []
    for lane in APP_LANES:
        output_file = paths.lanes / f"{lane}.jsonl"
        app_card_files.append(output_file)
        counts[lane] = generate_app_lane(
            units_file=units_file,
            output_file=output_file,
            rejected_file=paths.queues / f"rejected_generation_{lane}.jsonl",
            lane=lane,
            count=app_count_map[lane],
            settings=settings,
            llm=llm,
        )

    # Verification
    for lane in TRAIN_LANES + APP_LANES:
        schema_input = paths.lanes / f"{lane}.jsonl"
        counts[f"verify_{lane}"] = verify_lane(
            lane=lane,
            input_file=schema_input,
            output_file=paths.verified / f"{lane}_auto_checked.jsonl",
            rejected_file=paths.verified / f"{lane}_rejected.jsonl",
            fix_queue_file=paths.queues / f"{lane}_fix_queue.jsonl",
            human_review_file=paths.queues / f"{lane}_human_review_queue.jsonl",
            report_file=paths.reports / f"{lane}_verification_report.json",
            source_file=input_file,
            settings=settings,
            llm=llm if llm_judge else None,
            llm_judge=llm_judge,
        )

    counts["rag"] = build_rag_chunks(units_file, paths.rag / "chunks.jsonl")
    counts["offline"] = build_offline_bundle(units_file, app_card_files, paths.offline / "chapter_bundle.json", chapter_name)

    # Export app/runtime artifacts regardless of train_allowed; training exports require approval later.
    export_app_dir = paths.exports / "app_content"
    export_app_dir.mkdir(exist_ok=True)
    for lane in APP_LANES:
        src = paths.verified / f"{lane}_auto_checked.jsonl"
        if src.exists():
            shutil.copy2(src, export_app_dir / f"{lane}.jsonl")
    shutil.copy2(paths.rag / "chunks.jsonl", paths.exports / "rag" / "chunks.jsonl")
    shutil.copy2(paths.offline / "chapter_bundle.json", paths.exports / "offline" / "chapter_bundle.json")

    # Copy static app binding maps into run export.
    binding_dir = paths.exports / "manifests"
    for name in ["aspireace_surface_map.json", "engine_binding_map.json", "feature_flag_seed.json", "runtime_routes.json"]:
        copy_json_file(Path("app_binding") / name, binding_dir / name)

    outputs = {
        "source_units": str(units_file),
        "lanes_dir": str(paths.lanes),
        "verified_dir": str(paths.verified),
        "queues_dir": str(paths.queues),
        "rag_chunks": str(paths.rag / "chunks.jsonl"),
        "offline_bundle": str(paths.offline / "chapter_bundle.json"),
        "exports_dir": str(paths.exports),
    }
    manifest = write_manifest(paths.manifests / "run_manifest.json", run_id, input_file, "completed", outputs, counts, rights_summary)
    write_json(paths.reports / "run_report.json", {"run_id": run_id, "counts": counts, "rights_summary": rights_summary, "outputs": outputs})
    return {"run_id": run_id, "outputs": outputs, "counts": counts, "manifest": manifest}
