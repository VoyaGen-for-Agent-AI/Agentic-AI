import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node


def make_state(**overrides):
    state = {
        "messages": [HumanMessage(content="幫我安排住宿與預算")],
        "user_query": "幫我安排住宿與預算",
        "route": "unknown",
        "current_task": "",
        "next_step": "",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {},
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
    state.update(overrides)
    return state


def itinerary_result():
    return {
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
                        "reason": "符合戶外與輕鬆行程偏好。",
                    },
                ],
            }
        ],
        "ticket_cost_total": 300,
        "transport_hint": "以台中市區公車與步行為主。",
        "planning_reason": "行程集中於市區，符合兩天一夜且不要太趕的需求。",
    }


def booking_result():
    return {
        "hotels": [],
        "recommended_hotel": {
            "name": "台中車站附近商旅 A",
            "area": "台中車站",
            "price_per_night": 2100,
            "total_price": 2100,
            "rating": 4.2,
            "reason": "位於偏好區域 台中車站；符合每晚住宿預算；評分 4.2。",
        },
    }


def budget_result(status="comfortable"):
    return {
        "total_budget": 6000,
        "total_estimated_cost": 5100,
        "remaining_budget": 900,
        "over_budget_amount": 0,
        "status": status,
        "allocation": {
            "hotel_budget": 2400,
            "transport_budget": 1080,
            "food_budget": 1620,
            "activity_budget": 300,
            "buffer_budget": 600,
        },
        "breakdown": {
            "hotel": 2100,
            "transport": 500,
            "food": 1600,
            "activity": 300,
            "buffer": 600,
        },
        "suggestion": "目前預算充足，仍保留一定彈性。",
        "used_fallbacks": [],
    }


def test_final_response_with_booking_result():
    result = final_response_node(
        make_state(route="booking", booking_result=booking_result())
    )

    assert "台中車站附近商旅 A" in result["final_answer"]
    assert "台中車站" in result["final_answer"]
    assert "2100" in result["final_answer"]
    assert "推薦原因" in result["final_answer"]


def test_final_response_with_itinerary_result():
    result = final_response_node(
        make_state(route="itinerary", itinerary_result=itinerary_result())
    )

    assert "行程天數：2 天" in result["final_answer"]
    assert "Day 1" in result["final_answer"]
    assert "台中車站" in result["final_answer"]
    assert "審計新村" in result["final_answer"]
    assert "安排原因" in result["final_answer"]
    assert "交通提示" in result["final_answer"]
    assert "規劃理由" in result["final_answer"]


def test_final_response_with_budget_result():
    result = final_response_node(
        make_state(route="budget", budget_result=budget_result())
    )

    assert "總預算：6000 元" in result["final_answer"]
    assert "預估總花費：5100 元" in result["final_answer"]
    assert "住宿：2100 元" in result["final_answer"]
    assert "交通：500 元" in result["final_answer"]
    assert "飲食：1600 元" in result["final_answer"]
    assert "活動 / 門票：300 元" in result["final_answer"]
    assert "預留金：600 元" in result["final_answer"]
    assert "目前預算充足" in result["final_answer"]


def test_final_response_combines_booking_and_budget_results():
    result = final_response_node(
        make_state(
            route="booking",
            booking_result=booking_result(),
            budget_result=budget_result(),
        )
    )

    assert "住宿建議" in result["final_answer"]
    assert "台中車站附近商旅 A" in result["final_answer"]
    assert "預算估算" in result["final_answer"]
    assert "總預算：6000 元" in result["final_answer"]


def test_final_response_combines_itinerary_booking_and_budget_results():
    result = final_response_node(
        make_state(
            route="travel",
            itinerary_result=itinerary_result(),
            booking_result=booking_result(),
            budget_result=budget_result(),
        )
    )

    assert "一、行程安排" in result["final_answer"]
    assert "二、住宿建議" in result["final_answer"]
    assert "三、預算估算" in result["final_answer"]
    assert "四、總結建議" in result["final_answer"]
    assert "審計新村" in result["final_answer"]
    assert "台中車站附近商旅 A" in result["final_answer"]
    assert "總預算：6000 元" in result["final_answer"]


def test_final_response_with_over_budget_result():
    over_budget_result = budget_result(status="over_budget")
    over_budget_result["remaining_budget"] = -800
    over_budget_result["over_budget_amount"] = 800
    over_budget_result["suggestion"] = "目前預估超出總預算，建議改選平價住宿或更換住宿區域。"

    result = final_response_node(
        make_state(route="budget", budget_result=over_budget_result)
    )

    assert "已超出預算" in result["final_answer"]
    assert "超支金額：800 元" in result["final_answer"]
    assert "建議改選平價住宿" in result["final_answer"]
