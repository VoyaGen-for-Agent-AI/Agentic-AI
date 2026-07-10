import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import booking_worker
from agents.workers.booking_worker import booking_node, score_hotel
from agents.workers.budget_worker import allocate_budget


def make_state(**overrides):
    state = {
        "messages": [HumanMessage(content="幫我安排台中兩天一夜住宿")],
        "user_query": "幫我安排台中兩天一夜住宿",
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


def test_allocate_budget_default():
    allocation = allocate_budget(total_budget=6000, days=2, nights=1)

    assert allocation["hotel_budget"] == 2400
    assert allocation["transport_budget"] == 1080
    assert allocation["food_budget"] == 1620
    assert allocation["activity_budget"] == 300
    assert sum(allocation.values()) == 6000


def test_booking_node_returns_candidates():
    result = booking_node(make_state(destination="台中", total_budget=6000, nights=1))

    assert "booking_result" in result
    assert len(result["booking_result"]["hotels"]) >= 2
    assert result["booking_result"]["recommended_hotel"] is not None
    assert result["budget_allocation"]["hotel_budget"] == 2400
    assert result["current_task"] == "booking"
    assert result["next_step"] == "coder"


def test_booking_prefers_budget_friendly_hotel():
    result = booking_node(
        make_state(
            total_budget=3500,
            nights=1,
            preferred_areas=["一中街"],
            preference="省錢",
        )
    )

    recommended_hotel = result["booking_result"]["recommended_hotel"]
    hotel_budget = result["budget_allocation"]["hotel_budget"]

    assert recommended_hotel["price_per_night"] <= hotel_budget


def test_booking_prefers_preferred_area():
    station_hotel = {
        "name": "台中車站附近商旅 A",
        "area": "台中車站",
        "price_per_night": 2100,
        "rating": 4.2,
        "tags": ["交通方便", "近車站", "平價"],
    }
    same_price_other_area = {
        "name": "其他區域旅宿",
        "area": "七期",
        "price_per_night": 2100,
        "rating": 4.2,
        "tags": ["交通方便", "平價"],
    }

    station_score = score_hotel(
        station_hotel,
        hotel_budget=2400,
        preferred_areas=["台中車站"],
        preference="交通方便",
        nights=1,
    )
    other_score = score_hotel(
        same_price_other_area,
        hotel_budget=2400,
        preferred_areas=["台中車站"],
        preference="交通方便",
        nights=1,
    )

    assert station_score > other_score


def test_booking_empty_result(monkeypatch):
    monkeypatch.setattr(booking_worker, "TAICHUNG_HOTELS", [])

    result = booking_node(make_state())

    assert result["booking_result"] == {
        "hotels": [],
        "recommended_hotel": None,
    }
    assert result["execution_status"] == "empty_result"
    assert result["error_traceback"] == "No hotel candidates found"
    assert result["current_task"] == "booking"
