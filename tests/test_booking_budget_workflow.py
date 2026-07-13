import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node


def make_state():
    return {
        "messages": [HumanMessage(content="幫我安排台中兩天一夜住宿與預算")],
        "user_query": "幫我安排台中兩天一夜住宿與預算",
        "route": "booking",
        "current_task": "",
        "next_step": "booking",
        "destination": "台中",
        "total_budget": 6000,
        "days": 2,
        "nights": 1,
        "preferred_areas": ["台中車站", "逢甲"],
        "preference": "交通方便",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {"total_transport_cost": 500},
        "itinerary_result": {"ticket_cost_total": 300},
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


def test_booking_budget_workflow_generates_combined_final_answer():
    state = make_state()

    apply_update(state, booking_node(state))
    assert state["booking_result"]["recommended_hotel"]
    assert state["next_step"] == "final_response"

    apply_update(state, budget_node(state))
    assert state["budget_result"]["breakdown"]["hotel"] == state["booking_result"]["recommended_hotel"]["total_price"]
    assert state["next_step"] == "final_response"

    apply_update(state, final_response_node(state))

    assert "住宿建議" in state["final_answer"]
    assert state["booking_result"]["recommended_hotel"]["name"] in state["final_answer"]
    assert "預算估算" in state["final_answer"]
    assert "總預算：6000 元" in state["final_answer"]
    assert "住宿：" in state["final_answer"]
    assert "交通：" in state["final_answer"]
