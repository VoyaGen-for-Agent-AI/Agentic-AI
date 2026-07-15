import json
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import travel_worker
from agents.workers.budget_worker import budget_node
from agents.workers.travel_worker import itinerary_node


def make_state(**overrides):
    state = {
        "messages": [HumanMessage(content="我想從台北去台中兩天一夜，行程不要太趕。")],
        "user_query": "我想從台北去台中兩天一夜，行程不要太趕。",
        "route": "travel",
        "current_task": "",
        "next_step": "travel",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {
            "hotel_budget": 2400,
            "transport_budget": 1080,
            "food_budget": 1620,
            "activity_budget": 300,
            "buffer_budget": 600,
        },
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
        "total_budget": 6000,
        "days": 2,
        "nights": 1,
    }
    state.update(overrides)
    return state


def sample_itinerary():
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
        "transport_hint": "以台中市區公車與步行為主，景點集中避免移動過長。",
        "planning_reason": "行程集中於市區與逢甲周邊，符合兩天一夜且不要太趕的需求。",
    }


def test_itinerary_node_parses_valid_json(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps(sample_itinerary(), ensure_ascii=False))

    monkeypatch.setattr(travel_worker, "ChatOpenAI", FakeChatOpenAI)

    result = itinerary_node(make_state())

    assert result["itinerary_result"]["destination"] == "台中"
    assert result["itinerary_result"]["ticket_cost_total"] == 300
    assert result["travel_result"] == result["itinerary_result"]
    assert result["current_task"] == "travel"
    assert result["next_step"] == "final_response"


def test_itinerary_node_handles_invalid_json(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content="這不是 JSON")

    monkeypatch.setattr(travel_worker, "ChatOpenAI", FakeChatOpenAI)

    result = itinerary_node(make_state())

    assert result["execution_status"] == "error"
    assert result["error_traceback"] == "Invalid itinerary JSON"
    assert result["current_task"] == "travel"


def test_itinerary_result_can_feed_budget_worker():
    state = make_state(
        itinerary_result={"ticket_cost_total": 300},
        booking_result={
            "recommended_hotel": {
                "name": "台中車站附近商旅 A",
                "price_per_night": 2100,
                "total_price": 2100,
            }
        },
    )

    result = budget_node(state)

    assert result["budget_result"]["breakdown"]["activity"] == 300
