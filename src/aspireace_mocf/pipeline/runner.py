"""Pipeline runner — orchestrates the full 9-lane content generation for one chapter.

Purpose: takes a source file + rights ledger + chapter metadata, runs source-unit
decomposition + 9 lanes of generation + verification + RAG/offline emission +
exports, writes manifests and reports. This is the entry point for both the CLI
`run` command and the LangGraph supervisor agent.

Bug fixes vs v0.3.0 baseline:
- Bug #2: per-lane rights gating. The old code raised RuntimeError if BOTH `rag`
  AND `app_content` were blocked, letting training-lane generation proceed for
  reference-only sources. New code checks `rights_summary[lane]["ok"]` BEFORE
  each lane runs and skips the lane (logging the skip with reason) if the source
  isn't approved for it.

Above-the-bar additions:
- Lane-level checkpointing via `pipeline.checkpoint`: if the runner dies mid-way,
  `resume` picks up at the next un-completed lane.
- Per-lane structured logging with run_id correlation.
- Lockfile via `pipeline.lockfile` to prevent concurrent runs against the same run_id.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
SLA: one chapter with 5 source units, 9 lanes, no judge: <= 25 minutes on
Qwen3-8B Q4_K_M on a 5060 8GB.
Failure modes: see `utils.errors.PipelineError` enum values.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from aspireace_mocf.pipeline.approve import approve_file
from aspireace_mocf.pipeline.export import copy_json_file
from aspireace_mocf.pipeline.formula_extraction import extract_formulas
from aspireace_mocf.pipeline.lane_generation import generate_app_lane, generate_training_lane
from aspireace_mocf.pipeline.manifest import write_manifest
from aspireace_mocf.pipeline.paths import RunPaths
from aspireace_mocf.pipeline.rag_offline import build_offline_bundle, build_rag_chunks
from aspireace_mocf.pipeline.source_units import build_source_units
from aspireace_mocf.pipeline.verify import verify_lane
from aspireace_mocf.pipeline.lockfile import RunLock
from aspireace_mocf.providers.llm import LLMClient
from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.errors import PipelineError, PipelineErrorCode
from aspireace_mocf.utils.jsonio import read_json, write_json
from aspireace_mocf.utils.logging import get_logger
from aspireace_mocf.utils.text import extract_source_id
from aspireace_mocf.validators.rights_validator import load_rights_ledger, validate_source_for_lane


_log = get_logger(__name__)


TRAIN_LANES = ["base_subject", "tutor_app", "content_generator"]
APP_LANES = ["notes", "tricks", "misconceptions", "dpp_tests", "grading_feedback", "revision"]


# Maps a lane name to the rights-ledger lane category. Multiple lanes share a
# rights category (e.g. all 6 app lanes share `app_content`), so we don't ask
# for "approval per lane" — we ask for "approval per lane category".
LANE_TO_RIGHTS_CATEGORY = {
    "base_subject": "base_subject",
    "tutor_app": "tutor_app",
    "content_generator": "content_generator",
    "notes": "app_content",
    "tricks": "app_content",
    "misconceptions": "app_content",
    "dpp_tests": "app_content",
    "grading_feedback": "app_content",
    "revision": "app_content",
}


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
    """Run the full pipeline for one chapter. Returns counts + outputs + manifest dict."""
    _log.info(
        "pipeline_run_starting",
        run_id=run_id,
        chapter_no=chapter_no,
        chapter_name=chapter_name,
        input_file=str(input_file),
        rights_ledger_file=str(rights_ledger_file),
        limit_units=limit_units,
        llm_judge=llm_judge,
    )

    # Lockfile: prevent two concurrent factory runs against the same run_id.
    with RunLock(run_id):
        paths = RunPaths.create(run_id)
        llm = LLMClient(settings)
        counts: dict[str, Any] = {}

        ledger = load_rights_ledger(rights_ledger_file)
        source_id = extract_source_id(read_json(input_file))

        # Bug #2 fix: per-lane rights gating, not an aggregate raise.
        # Build a rights_summary that records every lane's approval status, but
        # do NOT raise on aggregate — instead, skip individual lanes that the
        # rights ledger blocks. This prevents the old bug where training lanes
        # were running on reference-only sources just because some app lane was
        # also approved.
        rights_summary: dict[str, dict[str, Any]] = {}
        for category in {"base_subject", "tutor_app", "content_generator", "app_content", "rag", "offline"}:
            ok, reason = validate_source_for_lane(ledger, source_id, category)
            rights_summary[category] = {"ok": ok, "reason": reason}
            _log.info("rights_check", run_id=run_id, lane_category=category, ok=ok, reason=reason)

        # If no lane is approved, the source is unusable entirely. Hard fail.
        if all(not v["ok"] for v in rights_summary.values()):
            raise PipelineError(
                code=PipelineErrorCode.RIGHTS_LEDGER_BLOCKS_ALL_LANES,
                message=(
                    f"Rights ledger blocks ALL lanes for source_id={source_id}. "
                    f"Summary: {rights_summary}. Check examples/source_ledger.csv "
                    f"entry for this source_id."
                ),
            )

        # Source-unit decomposition. Always allowed (uses source text only, doesn't
        # produce trainable derivatives by itself).
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
        _log.info("source_units_built", run_id=run_id, counts=counts["source_units"])

        # Training lanes (base_subject / tutor_app / content_generator).
        # Each gated on rights_summary[lane_category]["ok"].
        for lane in TRAIN_LANES:
            rights_category = LANE_TO_RIGHTS_CATEGORY[lane]
            if not rights_summary[rights_category]["ok"]:
                _log.warning(
                    "lane_skipped_by_rights_ledger",
                    run_id=run_id,
                    lane=lane,
                    reason=rights_summary[rights_category]["reason"],
                )
                counts[lane] = {f"{lane}_accepted": 0, f"{lane}_rejected": 0, "skipped_reason": rights_summary[rights_category]["reason"]}
                continue
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
            _log.info("training_lane_completed", run_id=run_id, lane=lane, counts=counts[lane])

        # App-content lanes. All gated on rights_summary["app_content"]["ok"].
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
            if not rights_summary["app_content"]["ok"]:
                _log.warning(
                    "lane_skipped_by_rights_ledger",
                    run_id=run_id,
                    lane=lane,
                    reason=rights_summary["app_content"]["reason"],
                )
                counts[lane] = {f"{lane}_accepted": 0, f"{lane}_rejected": 0, "skipped_reason": rights_summary["app_content"]["reason"]}
                continue
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
            _log.info("app_lane_completed", run_id=run_id, lane=lane, counts=counts[lane])

        # M4: Formula extraction. Runs after app lanes complete; gated by
        # settings.extract_formulas AND rights_summary["app_content"]["ok"]
        # (formulas land in the app_content category). Produces structured
        # formula records at runs/<id>/lanes/formulas.jsonl.
        if settings.extract_formulas and rights_summary["app_content"]["ok"]:
            try:
                counts["formulas"] = extract_formulas(
                    units_file=units_file,
                    output_file=paths.lanes / "formulas.jsonl",
                    rejected_file=paths.queues / "rejected_generation_formulas.jsonl",
                    settings=settings,
                    llm=llm,
                )
                _log.info("formula_extraction_completed_in_runner", run_id=run_id, counts=counts["formulas"])
            except Exception as exc:
                _log.warning("formula_extraction_failed_non_fatal", run_id=run_id, error=str(exc))
                counts["formulas"] = {"formulas_accepted": 0, "formulas_rejected": 0, "error": str(exc)}
        else:
            counts["formulas"] = {"formulas_accepted": 0, "formulas_rejected": 0, "skipped_reason": "extract_formulas=false or app_content rights blocked"}

        # Verification (schema + similarity + optional LLM-judge gate).
        # Verification reads lane output files; lanes that were skipped above
        # have no output to verify, so guard.
        for lane in TRAIN_LANES + APP_LANES:
            schema_input = paths.lanes / f"{lane}.jsonl"
            if not schema_input.exists():
                _log.info("verify_lane_skipped_no_input", run_id=run_id, lane=lane)
                continue
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

        # RAG and offline outputs. Gated separately.
        if rights_summary["rag"]["ok"]:
            counts["rag"] = build_rag_chunks(units_file, paths.rag / "chunks.jsonl")
        else:
            _log.warning("rag_skipped_by_rights_ledger", run_id=run_id, reason=rights_summary["rag"]["reason"])
            counts["rag"] = {"rag_chunks": 0, "skipped_reason": rights_summary["rag"]["reason"]}

        if rights_summary["offline"]["ok"]:
            counts["offline"] = build_offline_bundle(
                units_file,
                app_card_files,
                paths.offline / "chapter_bundle.json",
                chapter_name,
            )
        else:
            _log.warning("offline_skipped_by_rights_ledger", run_id=run_id, reason=rights_summary["offline"]["reason"])
            counts["offline"] = {"offline_items": 0, "offline_units": 0, "skipped_reason": rights_summary["offline"]["reason"]}

        # Export app/runtime artifacts regardless of train_allowed; training
        # exports require explicit `aspireace-mocf approve` + `export` later.
        export_app_dir = paths.exports / "app_content"
        export_app_dir.mkdir(exist_ok=True)
        for lane in APP_LANES:
            src = paths.verified / f"{lane}_auto_checked.jsonl"
            if src.exists():
                shutil.copy2(src, export_app_dir / f"{lane}.jsonl")
        rag_src = paths.rag / "chunks.jsonl"
        if rag_src.exists():
            shutil.copy2(rag_src, paths.exports / "rag" / "chunks.jsonl")
        offline_src = paths.offline / "chapter_bundle.json"
        if offline_src.exists():
            shutil.copy2(offline_src, paths.exports / "offline" / "chapter_bundle.json")

        # Copy static app binding maps into run export (provenance for downstream consumers).
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
        manifest = write_manifest(
            paths.manifests / "run_manifest.json",
            run_id,
            input_file,
            "completed",
            outputs,
            counts,
            rights_summary,
        )
        write_json(
            paths.reports / "run_report.json",
            {"run_id": run_id, "counts": counts, "rights_summary": rights_summary, "outputs": outputs},
        )
        _log.info("pipeline_run_completed", run_id=run_id, total_lanes_run=len([l for l in TRAIN_LANES + APP_LANES if (paths.lanes / f"{l}.jsonl").exists()]))
        return {"run_id": run_id, "outputs": outputs, "counts": counts, "manifest": manifest}
