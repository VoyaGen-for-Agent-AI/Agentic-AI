import json
import os
import re

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.spot_worker import spot_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.trip_parser_worker import trip_parser_node
from agents.workers.travel_worker import travel_node
from agents.workers.weather_worker import weather_node
from core.observability import get_langfuse_callbacks
from core.state import AgentState


load_dotenv()
if not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
    print("警告：找不到 OPENROUTER_API_KEY 或 OPENAI_API_KEY！")

app = FastAPI()

# 允許本機前端 (Vite dev server) 跨埠呼叫 /chat。
# demo 用途，開發環境放行 localhost:5173；正式部署請改成實際網域白名單。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# Demo-safe graph:
# trip_parser -> weather fallback -> spot -> booking -> traffic fallback
# -> travel fallback -> budget -> final_response
workflow = StateGraph(AgentState)

workflow.add_node("trip_parser", trip_parser_node)
workflow.add_node("weather", weather_node)
workflow.add_node("spot", spot_node)
workflow.add_node("booking", booking_node)
workflow.add_node("traffic", traffic_node)
workflow.add_node("travel", travel_node)
workflow.add_node("budget", budget_node)
workflow.add_node("final_response", final_response_node)

workflow.set_entry_point("trip_parser")
workflow.add_edge("trip_parser", "weather")
workflow.add_edge("weather", "spot")
workflow.add_edge("spot", "booking")
workflow.add_edge("booking", "traffic")
workflow.add_edge("traffic", "travel")
workflow.add_edge("travel", "budget")
workflow.add_edge("budget", "final_response")
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
