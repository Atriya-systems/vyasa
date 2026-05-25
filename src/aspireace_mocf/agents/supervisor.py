from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from aspireace_mocf.pipeline.runner import run_pipeline
from aspireace_mocf.settings import Settings
from aspireace_mocf.utils.jsonio import write_json


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
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    def pipeline_node(state: AgentState) -> AgentState:
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
        return state

    def supervisor_node(state: AgentState) -> AgentState:
        counts = state.get("result", {}).get("counts", {})
        accepted = 0
        rejected = 0
        fix_or_human = 0
        for value in counts.values():
            if isinstance(value, dict):
                for key, num in value.items():
                    if "accepted" in key or "source_units" in key or "rag_chunks" in key or "offline_items" in key:
                        accepted += int(num)
                    if "rejected" in key:
                        rejected += int(num)
                    if "fix_required" in key or "human_review" in key:
                        fix_or_human += int(num)
        if accepted == 0 and state.get("retries", 0) < state.get("max_retries", 2):
            state["decision"] = "retry"
        elif fix_or_human > 0 or rejected > accepted:
            state["decision"] = "human_review"
        else:
            state["decision"] = "finish"
        return state

    def human_gate_node(state: AgentState) -> AgentState:
        if state.get("human_in_loop") and state.get("decision") == "human_review":
            interrupt({
                "message": "Human review required. Inspect queues, approve/fix records, then resume.",
                "run_id": state["run_id"],
                "queues_dir": f"runs/{state['run_id']}/queues",
                "verified_dir": f"runs/{state['run_id']}/verified",
            })
        state["status"] = "human_review_routed"
        return state

    def retry_node(state: AgentState) -> AgentState:
        state["retries"] = int(state.get("retries", 0)) + 1
        return pipeline_node(state)

    def finish_node(state: AgentState) -> AgentState:
        state["status"] = "finished"
        write_json(Path("runs") / state["run_id"] / "agent_summary.json", dict(state))
        return state

    def route_after_supervisor(state: AgentState) -> Literal["retry", "human", "finish"]:
        if state.get("decision") == "retry":
            return "retry"
        if state.get("decision") == "human_review":
            return "human"
        return "finish"

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

    compiled = graph.compile(checkpointer=MemorySaver())
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
    }
    return compiled.invoke(initial, config={"configurable": {"thread_id": run_id}})
