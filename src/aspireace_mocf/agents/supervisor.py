"""LangGraph supervisor agent — runs the pipeline with retry + human-in-loop.

Purpose: wrap `pipeline.runner.run_pipeline` in a state machine that can decide
to retry, escalate to human review, or finish based on per-lane outcomes.

Bug fixes vs v0.3.0 baseline:
- Bug #4: per-lane retry decisions. The old supervisor retried only when
  TOTAL accepted across all lanes was zero — meaning if 8 of 9 lanes succeeded
  and 1 silently produced zero records, the supervisor finished anyway. New
  logic checks each lane individually and retries if ANY lane has zero
  accepted records (up to max_retries).

Above-the-bar additions:
- SqliteSaver checkpointer (was MemorySaver). Persists agent state to
  `runs/<run_id>/agent_state.sqlite` so a process death doesn't lose the
  supervisor's decision history.
- Structured logging at every node transition.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
SLA: supervisor overhead <= 200ms per node transition.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from aspireace_mocf.pipeline.runner import APP_LANES, TRAIN_LANES, run_pipeline
from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.jsonio import write_json
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


class AgentState(TypedDict, total=False):
    input_file: str
    rights_ledger_file: str
    run_id: str
    chapter_no: int
    chapter_name: str
    limit_units: int
    llm_judge: bool
    human_in_loop: bool
    retries: int
    max_retries: int
    result: dict[str, Any]
    decision: str
    status: str
    failed_lanes: list[str]  # Bug #4 fix: track which lanes had zero accepted


ALL_LANES = TRAIN_LANES + APP_LANES


def _per_lane_failures(counts: dict[str, Any]) -> list[str]:
    """Return list of lane names that produced zero accepted records.

    A lane "failed" in this sense if:
        - It ran (no `skipped_reason` in its count entry)
        - AND `<lane>_accepted` is 0

    Lanes intentionally skipped by the rights ledger are NOT counted as failures.
    """
    failed: list[str] = []
    for lane in ALL_LANES:
        lane_counts = counts.get(lane)
        if not isinstance(lane_counts, dict):
            continue
        if lane_counts.get("skipped_reason"):
            continue
        accepted_key = f"{lane}_accepted"
        if lane_counts.get(accepted_key, 0) == 0:
            failed.append(lane)
    return failed


def run_agent(
    *,
    input_file: Path,
    rights_ledger_file: Path,
    run_id: str,
    chapter_no: int,
    chapter_name: str,
    settings: Settings,
    limit_units: int = 0,
    llm_judge: bool = False,
    human_in_loop: bool = False,
) -> dict[str, Any]:
    """Run the pipeline under a LangGraph supervisor with retry + human gate.

    Returns the final state dict after the graph completes (or interrupts).
    """
    # Lazy imports — LangGraph is a heavy dep only needed when the user
    # explicitly opts into agent mode. This keeps CLI-only invocations fast.
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    # ----- node implementations -----

    def pipeline_node(state: AgentState) -> AgentState:
        _log.info("agent_node_pipeline_start", run_id=state["run_id"], retries=state.get("retries", 0))
        state["result"] = run_pipeline(
            input_file=Path(state["input_file"]),
            rights_ledger_file=Path(state["rights_ledger_file"]),
            run_id=state["run_id"],
            chapter_no=int(state["chapter_no"]),
            chapter_name=state["chapter_name"],
            settings=settings,
            limit_units=int(state.get("limit_units", 0)),
            llm_judge=bool(state.get("llm_judge", False)),
        )
        state["status"] = "pipeline_completed"
        _log.info("agent_node_pipeline_end", run_id=state["run_id"])
        return state

    def supervisor_node(state: AgentState) -> AgentState:
        counts = state.get("result", {}).get("counts", {})
        failed_lanes = _per_lane_failures(counts)
        state["failed_lanes"] = failed_lanes

        # Aggregate counts to inform the human-vs-finish branch.
        fix_or_human = 0
        rejected = 0
        accepted = 0
        for value in counts.values():
            if isinstance(value, dict):
                for key, num in value.items():
                    if isinstance(num, int):
                        if "accepted" in key or key == "source_units" or key == "rag_chunks" or key == "offline_items":
                            accepted += num
                        if "rejected" in key:
                            rejected += num
                        if "fix_required" in key or "human_review" in key:
                            fix_or_human += num

        # Bug #4 fix: retry if ANY lane has zero accepted (not just when ALL do).
        if failed_lanes and state.get("retries", 0) < state.get("max_retries", 2):
            state["decision"] = "retry"
            _log.warning(
                "agent_supervisor_retry",
                run_id=state["run_id"],
                failed_lanes=failed_lanes,
                retries_so_far=state.get("retries", 0),
                max_retries=state.get("max_retries", 2),
            )
        elif fix_or_human > 0 or rejected > accepted:
            state["decision"] = "human_review"
            _log.info(
                "agent_supervisor_human_review",
                run_id=state["run_id"],
                fix_or_human=fix_or_human,
                rejected=rejected,
                accepted=accepted,
                failed_lanes=failed_lanes,
            )
        else:
            state["decision"] = "finish"
            _log.info(
                "agent_supervisor_finish",
                run_id=state["run_id"],
                accepted=accepted,
                rejected=rejected,
            )
        return state

    def human_gate_node(state: AgentState) -> AgentState:
        if state.get("human_in_loop") and state.get("decision") == "human_review":
            _log.info("agent_node_human_interrupt", run_id=state["run_id"])
            interrupt({
                "message": "Human review required. Inspect queues, approve/fix records, then resume.",
                "run_id": state["run_id"],
                "queues_dir": f"runs/{state['run_id']}/queues",
                "verified_dir": f"runs/{state['run_id']}/verified",
                "failed_lanes": state.get("failed_lanes", []),
            })
        state["status"] = "human_review_routed"
        return state

    def retry_node(state: AgentState) -> AgentState:
        state["retries"] = int(state.get("retries", 0)) + 1
        _log.info(
            "agent_node_retry",
            run_id=state["run_id"],
            retries=state["retries"],
            failed_lanes=state.get("failed_lanes", []),
        )
        return pipeline_node(state)

    def finish_node(state: AgentState) -> AgentState:
        state["status"] = "finished"
        write_json(Path("runs") / state["run_id"] / "agent_summary.json", dict(state))
        _log.info("agent_node_finish", run_id=state["run_id"])
        return state

    def route_after_supervisor(state: AgentState) -> Literal["retry", "human", "finish"]:
        if state.get("decision") == "retry":
            return "retry"
        if state.get("decision") == "human_review":
            return "human"
        return "finish"

    # ----- graph wiring -----

    graph = StateGraph(AgentState)
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("human", human_gate_node)
    graph.add_node("retry", retry_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", "supervisor")
    graph.add_conditional_edges("supervisor", route_after_supervisor, {"retry": "retry", "human": "human", "finish": "finish"})
    graph.add_edge("retry", "supervisor")
    graph.add_edge("human", "finish")
    graph.add_edge("finish", END)

    # SqliteSaver: persistent checkpoint store so a process death doesn't lose state.
    # File lives in the run dir for traceability.
    checkpoint_db = Path("runs") / run_id / "agent_state.sqlite"
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        initial: AgentState = {
            "input_file": str(input_file),
            "rights_ledger_file": str(rights_ledger_file),
            "run_id": run_id,
            "chapter_no": chapter_no,
            "chapter_name": chapter_name,
            "limit_units": limit_units,
            "llm_judge": llm_judge,
            "human_in_loop": human_in_loop,
            "retries": 0,
            "max_retries": settings.agent_max_retries,
            "status": "started",
            "failed_lanes": [],
        }
        return compiled.invoke(initial, config={"configurable": {"thread_id": run_id}})
