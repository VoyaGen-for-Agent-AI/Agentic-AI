import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.trip_parser_worker import trip_parser_node
from core.observability import get_langfuse_callbacks


QUERY = "我想這週末(7/18~7/19)從台北(台北車站出發)去台中兩天一夜，一人總預算 6000 元，希望行程不要太趕，想去戶外景點，也幫我找住宿"

MOCK_ITINERARY_RESULT = {
    "destination": "台中",
    "days": 2,
    "style": "relaxed",
    "schedule": [
        {
            "day": 1,
            "items": [
                {
                    "time": "10:00",
                    "place": "台中車站",
                    "activity": "抵達與寄放行李",
                    "type": "transport",
                    "estimated_cost": 0,
                    "reason": "作為抵達點，方便後續市區移動。",
                },
                {
                    "time": "11:00",
                    "place": "審計新村",
                    "activity": "散步、拍照與逛文創小店",
                    "type": "outdoor",
                    "estimated_cost": 0,
                    "reason": "符合戶外景點與不要太趕的偏好。",
                },
            ],
        },
        {
            "day": 2,
            "items": [
                {
                    "time": "10:00",
                    "place": "草悟道",
                    "activity": "散步與咖啡店休息",
                    "type": "outdoor",
                    "estimated_cost": 300,
                    "reason": "節奏輕鬆，適合回程前安排。",
                }
            ],
        },
    ],
    "ticket_cost_total": 300,
    "transport_hint": "以台中市區公車與步行為主，景點集中避免移動過長。",
    "planning_reason": "行程集中於市區與逢甲周邊，符合兩天一夜且不要太趕的需求。",
}


def has_env(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def configure_openrouter_key() -> bool:
    if has_env("OPENAI_API_KEY"):
        return True

    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        os.environ["OPENAI_API_KEY"] = openrouter_key
        return True

    return False


def apply_update(state: dict, update: dict) -> None:
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]


def run_mock_demo() -> dict:
    state = {
        "messages": [HumanMessage(content=QUERY)],
        "user_query": QUERY,
        "route": "travel",
        "current_task": "",
        "next_step": "trip_parser",
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {"total_transport_cost": 500},
        "itinerary_result": MOCK_ITINERARY_RESULT,
        "execution_status": "success",
        "error_traceback": "",
        "final_answer": "",
    }

    apply_update(state, trip_parser_node(state))  # type: ignore[arg-type]
    state["itinerary_result"] = MOCK_ITINERARY_RESULT
    state["travel_result"] = MOCK_ITINERARY_RESULT
    apply_update(state, booking_node(state))  # type: ignore[arg-type]
    apply_update(state, budget_node(state))  # type: ignore[arg-type]
    apply_update(state, final_response_node(state))  # type: ignore[arg-type]
    return state


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    callbacks = get_langfuse_callbacks()
    if callbacks:
        print("Langfuse callbacks enabled.")
    else:
        print("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured or unavailable; continuing without Langfuse trace.")

    print(f"query: {QUERY}")

    if configure_openrouter_key():
        try:
            from main import app_graph

            result = app_graph.invoke(
                {"messages": [HumanMessage(content=QUERY)]},
                config={"callbacks": callbacks},
            )
        except Exception as exc:
            print("app_graph.invoke failed. Check OPENROUTER_API_KEY or OPENAI_API_KEY, model settings, and network access.")
            print(f"error: {exc}")
            return 1
    else:
        print("OPENROUTER_API_KEY or OPENAI_API_KEY is not set; app_graph.invoke requires an LLM key.")
        print("Running local mock demo instead.")
        result = run_mock_demo()

    final_answer = result.get("final_answer")
    if not final_answer and result.get("messages"):
        final_answer = result["messages"][-1].content

    print("\nfinal_answer:")
    print(final_answer or result)
    print("\nOpen Langfuse Cloud -> Project -> Traces to inspect the workflow trace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
