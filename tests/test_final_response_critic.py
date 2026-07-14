import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node


def make_state(**overrides):
    state = {
        "messages": [HumanMessage(content="請幫我診斷錯誤")],
        "user_query": "請幫我診斷錯誤",
        "route": "unknown",
        "current_task": "",
        "next_step": "",
        "trip_request": {},
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "itinerary_result": {},
        "booking_result": {},
        "budget_result": {},
        "budget_allocation": {},
        "transport_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "critic_feedback": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }
    state.update(overrides)
    return state


def critic_feedback():
    return {
        "error_type": "invalid_json",
        "reason": "The agent output is not valid JSON.",
        "fix_strategy": "Ensure the AI itinerary agent only outputs valid JSON without Markdown or extra text.",
        "should_retry": True,
        "fallback_strategy": "Use mock itinerary_result and continue booking/budget flow.",
    }


def itinerary_result():
    return {
        "destination": "台中",
        "days": 2,
        "schedule": [
            {
                "day": 1,
                "items": [
                    {
                        "time": "10:00",
                        "place": "台中車站",
                        "activity": "抵達",
                        "reason": "方便後續移動。",
                    }
                ],
            }
        ],
        "ticket_cost_total": 300,
        "transport_hint": "以公車為主。",
        "planning_reason": "行程不要太趕。",
    }


def booking_result():
    return {
        "recommended_hotel": {
            "name": "台中車站附近商旅 A",
            "area": "台中車站",
            "price_per_night": 2100,
            "total_price": 2100,
            "rating": 4.2,
            "reason": "符合住宿預算。",
        }
    }


def budget_result():
    return {
        "total_budget": 6000,
        "total_estimated_cost": 5100,
        "remaining_budget": 900,
        "over_budget_amount": 0,
        "status": "comfortable",
        "breakdown": {
            "hotel": 2100,
            "transport": 500,
            "food": 1600,
            "activity": 300,
            "buffer": 600,
        },
        "suggestion": "目前預算充足，仍保留一定彈性。",
    }


def test_final_response_with_critic_feedback_only():
    result = final_response_node(make_state(critic_feedback=critic_feedback()))

    assert "系統診斷" in result["final_answer"]
    assert "invalid_json" in result["final_answer"]
    assert "The agent output is not valid JSON." in result["final_answer"]
    assert "Ensure the AI itinerary agent" in result["final_answer"]
    assert "Use mock itinerary_result" in result["final_answer"]


def test_final_response_appends_critic_feedback_to_trip_plan():
    result = final_response_node(
        make_state(
            itinerary_result=itinerary_result(),
            booking_result=booking_result(),
            budget_result=budget_result(),
            critic_feedback=critic_feedback(),
        )
    )

    assert "一、行程安排" in result["final_answer"]
    assert "住宿建議" in result["final_answer"]
    assert "預算估算" in result["final_answer"]
    assert "系統診斷" in result["final_answer"]
    assert "invalid_json" in result["final_answer"]
