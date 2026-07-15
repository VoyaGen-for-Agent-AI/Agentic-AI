import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.budget_worker import (
    budget_node,
    calculate_actual_cost,
    evaluate_budget,
    generate_budget_suggestion,
)


def make_state(**overrides):
    state = {
        "messages": [HumanMessage(content="幫我估算台中兩天一夜總預算")],
        "user_query": "幫我估算台中兩天一夜總預算",
        "route": "budget",
        "current_task": "",
        "next_step": "budget",
        "total_budget": 6000,
        "days": 2,
        "nights": 1,
        "preference": "交通方便",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {
            "recommended_hotel": {
                "name": "台中車站附近商旅 A",
                "price_per_night": 2100,
                "total_price": 2100,
            }
        },
        "budget_allocation": {
            "hotel_budget": 2400,
            "transport_budget": 1080,
            "food_budget": 1620,
            "activity_budget": 300,
            "buffer_budget": 600,
        },
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
    state.update(overrides)
    return state


def test_calculate_actual_cost_with_booking_result():
    result = calculate_actual_cost(make_state())

    assert result["breakdown"]["hotel"] == 2100
    assert result["total_estimated_cost"] == 2100 + 500 + 1600 + 300 + 600
    assert result["remaining_budget"] == 900


def test_budget_status_comfortable():
    result = evaluate_budget(total_budget=6000, total_estimated_cost=4500)

    assert result["status"] == "comfortable"
    assert result["remaining_budget"] == 1500
    assert result["over_budget_amount"] == 0


def test_budget_status_tight():
    result = evaluate_budget(total_budget=6000, total_estimated_cost=5600)

    assert result["status"] == "tight"
    assert result["remaining_budget"] == 400


def test_budget_status_over_budget():
    evaluation = evaluate_budget(total_budget=6000, total_estimated_cost=6800)
    suggestion = generate_budget_suggestion(
        evaluation["status"],
        6000,
        {
            "hotel": 3200,
            "transport": 800,
            "food": 1600,
            "activity": 300,
            "buffer": 900,
        },
        {
            "hotel_budget": 2400,
            "transport_budget": 1080,
            "food_budget": 1620,
            "activity_budget": 300,
            "buffer_budget": 600,
        },
    )

    assert evaluation["status"] == "over_budget"
    assert evaluation["remaining_budget"] < 0
    assert "建議" in suggestion


def test_breakdown_sum_equals_total():
    result = calculate_actual_cost(make_state())

    assert sum(result["breakdown"].values()) == result["total_estimated_cost"]


def test_budget_node_uses_fallbacks():
    state = make_state(
        transport_result={},
        itinerary_result={},
    )

    result = budget_node(state)

    assert result["budget_result"]["breakdown"]["transport"] == 1080
    assert result["budget_result"]["breakdown"]["activity"] == 300
    assert "transport_cost" in result["budget_result"]["used_fallbacks"]
    assert "activity_cost" in result["budget_result"]["used_fallbacks"]


def test_budget_node_returns_budget_result():
    result = budget_node(make_state())

    assert "budget_result" in result
    assert "breakdown" in result["budget_result"]
    assert "allocation" in result["budget_result"]
    assert result["current_task"] == "budget"
    assert result["next_step"] == "final_response"


def test_budget_node_handles_invalid_total_budget():
    result = budget_node(make_state(total_budget="abc"))

    assert result == {
        "execution_status": "error",
        "error_traceback": "Invalid total_budget",
        "current_task": "budget",
        "next_step": "FINISH",
    }
