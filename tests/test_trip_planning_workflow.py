import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
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
                    "activity": "散步與逛文創小店",
                    "type": "outdoor",
                    "estimated_cost": 0,
                    "reason": "符合戶外景點與不要太趕的偏好。",
                },
            ],
        }
    ],
    "ticket_cost_total": 300,
    "transport_hint": "以市區公車與步行為主。",
    "planning_reason": "景點集中，適合兩天一夜輕鬆安排。",
}


def make_state():
    return {
        "messages": [HumanMessage(content=DEMO_QUERY)],
        "user_query": DEMO_QUERY,
        "route": "travel",
        "current_task": "",
        "next_step": "trip_parser",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {"total_transport_cost": 500},
        "itinerary_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def apply_update(state, update):
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]
    return state


def test_trip_planning_mock_workflow_generates_complete_recommendation():
    state = make_state()

    apply_update(state, trip_parser_node(state))
    state["itinerary_result"] = MOCK_ITINERARY_RESULT
    state["travel_result"] = MOCK_ITINERARY_RESULT

    apply_update(state, booking_node(state))
    apply_update(state, budget_node(state))
    apply_update(state, final_response_node(state))

    assert state["trip_request"]
    assert state["itinerary_result"]
    assert state["booking_result"]
    assert state["budget_result"]
    assert "台中" in state["final_answer"]
    assert "行程" in state["final_answer"]
    assert "住宿" in state["final_answer"]
    assert "預算" in state["final_answer"]
    assert "6000" in state["final_answer"]
