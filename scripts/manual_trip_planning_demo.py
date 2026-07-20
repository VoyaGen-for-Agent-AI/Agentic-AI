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
from agents.workers.travel_worker import itinerary_node
from agents.workers.trip_parser_worker import trip_parser_node


DEMO_QUERY = "我想這週末(7/18~7/19)從台北(台北車站出發)去台中兩天一夜，一人總預算 6000 元，希望行程不要太趕，想去戶外景點，也幫我找住宿"

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
                    "activity": "散步與欣賞街區景觀",
                    "type": "outdoor",
                    "estimated_cost": 0,
                    "reason": "節奏輕鬆，適合回程前安排。",
                }
            ],
        },
    ],
    "ticket_cost_total": 0,
    "transport_hint": "以台中市區公車與步行為主，景點集中避免移動過長。",
    "planning_reason": "行程集中於市區與逢甲周邊，符合兩天一夜且不要太趕的需求。",
    "source": "mock_fallback",
    "source_detail": "Live itinerary generation unavailable or failed; using fallback itinerary.",
    "validation_status": "fallback",
    "validation_notes": ["manual demo mock itinerary"],
}


def _has_api_key(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _configure_openrouter_key() -> bool:
    if _has_api_key("OPENAI_API_KEY"):
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


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    use_live_itinerary = os.getenv("USE_LIVE_ITINERARY") == "1"
    print("AI itinerary live mode enabled" if use_live_itinerary else "Mock itinerary mode")

    state = {
        "messages": [HumanMessage(content=DEMO_QUERY)],
        "user_query": DEMO_QUERY,
        "route": "travel",
        "current_task": "",
        "next_step": "trip_parser",
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {"total_transport_cost": 500},
        "itinerary_result": {},
        "execution_status": "success",
        "error_traceback": "",
        "final_answer": "",
    }

    apply_update(state, trip_parser_node(state))  # type: ignore[arg-type]

    if use_live_itinerary:
        if not _configure_openrouter_key():
            print("OPENROUTER_API_KEY or OPENAI_API_KEY is not set. Falling back to mock itinerary.")
            state["itinerary_result"] = MOCK_ITINERARY_RESULT
            state["travel_result"] = MOCK_ITINERARY_RESULT
        else:
            apply_update(state, itinerary_node(state))  # type: ignore[arg-type]
            if state.get("execution_status") == "error":
                print(f"itinerary error: {state.get('error_traceback', '')}")
                return
            itinerary_result = state.get("itinerary_result", {})
            if isinstance(itinerary_result, dict):
                print(f"itinerary_result source: {itinerary_result.get('source', 'unknown')}")
    else:
        state["itinerary_result"] = MOCK_ITINERARY_RESULT
        state["travel_result"] = MOCK_ITINERARY_RESULT
        print("itinerary_result source: mock_fallback")

    apply_update(state, booking_node(state))  # type: ignore[arg-type]
    apply_update(state, budget_node(state))  # type: ignore[arg-type]
    apply_update(state, final_response_node(state))  # type: ignore[arg-type]

    print("trip_request:")
    print(state.get("trip_request", {}))
    print("\nitinerary_result:")
    print(state.get("itinerary_result", {}))
    itinerary_result = state.get("itinerary_result", {})
    if isinstance(itinerary_result, dict):
        print("\nitinerary validation:")
        for key in ("source", "model", "validation_status", "validation_notes", "ticket_cost_total"):
            print(f"{key}: {itinerary_result.get(key)}")
    print("\nbooking_result:")
    print(state.get("booking_result", {}))
    print("\nbudget_result:")
    print(state.get("budget_result", {}))
    print("\nfinal_answer:")
    print(state.get("final_answer", ""))


if __name__ == "__main__":
    main()
