import json
import os
import re

from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from agents.final_response import final_response_node
from agents.stage_graph import make_stage_node
from agents.supervisor import route_next, supervisor_node as stage_supervisor_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.schedule_worker import schedule_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.travel_worker import travel_node
from agents.workers.weather_worker import weather_node
from core.observability import get_langfuse_callbacks
from core.state import AgentState


load_dotenv()
if not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
    print("警告：找不到 OPENROUTER_API_KEY 或 OPENAI_API_KEY！")

app = FastAPI()


VALID_ROUTES = {
    "weather",
    "travel",
    "booking",
    "budget",
    "scheduler",
    "traffic",
    "safety",
    "final_response",
    "FINISH",
}

ROUTE_ALIASES = {
    "itinerary": "travel",
    "trip": "travel",
    "trip_planning": "travel",
    "hotel": "booking",
    "accommodation": "booking",
    "lodging": "booking",
    "finance": "budget",
    "cost": "budget",
    "expense": "budget",
}

# Backward-compatible hook for tests/manual experiments that monkeypatch a supervisor chain.
supervisor_chain = None


def normalize_route(raw_output) -> str:
    if hasattr(raw_output, "content"):
        return normalize_route(raw_output.content)

    if isinstance(raw_output, dict):
        raw_route = raw_output.get("next") or raw_output.get("route") or raw_output.get("next_step")
        return normalize_route(raw_route)

    for attr in ("next", "route", "next_step"):
        if hasattr(raw_output, attr):
            return normalize_route(getattr(raw_output, attr))

    if raw_output is None:
        return "travel"

    raw_text = str(raw_output).strip()
    if not raw_text:
        return "travel"

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        return normalize_route(parsed)

    input_value_match = re.search(r"input_value=['\"]([^'\"]+)['\"]", raw_text)
    if input_value_match:
        return normalize_route(input_value_match.group(1))

    normalized_text = raw_text.strip().strip('"').strip("'")
    if normalized_text in VALID_ROUTES:
        return normalized_text

    alias_key = normalized_text.lower().replace("-", "_").replace(" ", "_")
    return ROUTE_ALIASES.get(alias_key, "travel")


def supervisor_node(state: AgentState):
    """Compatibility route parser node; parent graph uses stage_supervisor_node."""
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else state.get("user_query", "")
    try:
        if supervisor_chain is None:
            normalized_route = normalize_route(state.get("next_step") or state.get("route"))
        else:
            result = supervisor_chain.invoke({"input": user_input})
            normalized_route = normalize_route(result)
        return {
            "route": normalized_route,
            "next_step": normalized_route,
            "current_task": "supervisor",
        }
    except Exception as error:
        normalized_route = normalize_route(error)
        return {
            "route": normalized_route,
            "next_step": normalized_route,
            "current_task": "supervisor",
            "execution_status": "fallback",
            "error_traceback": str(error),
        }


# ---------------------------------------------------------------------------
# 構建 Graph 狀態機
#
# supervisor 是確定性的編排 hub；每個 stage 都是一張獨立子圖
# (worker -> coder -> e2b_sandbox -> parser)，由 make_stage_node 包裝後只把該 stage
# 的 result 冒泡回父圖。因此 travel / booking 可以平行執行而不會互相覆蓋狀態。
# ---------------------------------------------------------------------------
workflow = StateGraph(AgentState)

workflow.add_node("supervisor", stage_supervisor_node)
workflow.add_node("budget", make_stage_node(budget_node, "budget_result", "budget"))
workflow.add_node("weather", make_stage_node(weather_node, "weather_result", "weather"))
workflow.add_node("travel", make_stage_node(travel_node, "travel_result", "travel"))
workflow.add_node("booking", make_stage_node(booking_node, "booking_result", "booking"))
workflow.add_node("traffic", make_stage_node(traffic_node, "traffic_result", "traffic"))
workflow.add_node("scheduler", make_stage_node(schedule_node, "scheduler_result", "scheduler"))
workflow.add_node("final_response", final_response_node)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    route_next,
    {
        "budget": "budget",
        "weather": "weather",
        "travel": "travel",
        "booking": "booking",
        "traffic": "traffic",
        "scheduler": "scheduler",
        "FINISH": "final_response",
    },
)

for stage in ("budget", "weather", "travel", "booking", "traffic", "scheduler"):
    workflow.add_edge(stage, "supervisor")

workflow.add_edge("final_response", END)

app_graph = workflow.compile()


@app.get("/chat/{query}")
def chat_test(query: str):
    config = {"callbacks": get_langfuse_callbacks()}
    result = app_graph.invoke({"messages": [HumanMessage(content=query)]}, config)  # type: ignore

    stages = []
    for log in result.get("stage_logs", []):
        result_key = log.get("result_key", "")
        stages.append({
            "stage": log.get("stage", ""),
            "status": log.get("status", ""),
            "has_result": log.get("has_result", False),
            "code_chars": log.get("code_chars", 0),
            "result": result.get(result_key, {}) if result_key else {},
        })

    return {
        "response": result["messages"][-1].content,
        "budget_tier": result.get("budget_tier", ""),
        "stages": stages,
    }
