import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import traffic_worker
from agents.workers.budget_worker import budget_node
from agents.workers.traffic_worker import traffic_node


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _state():
    return {
        "origin": "台北",
        "departure_station": "台北車站",
        "destination": "台中",
        "trip_request": {"departure_station": "台北車站", "destination": "台中"},
        "spot_result": {"spots": [{"name": "高美濕地"}]},
        "itinerary_result": {},
    }


def _configure_tavily(monkeypatch):
    monkeypatch.setenv("USE_LIVE_TRAFFIC", "1")
    monkeypatch.setenv("TRAFFIC_PROVIDER", "tavily")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_tavily_missing_key_falls_back(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = traffic_node(_state())

    assert result["traffic_result"]["source"] == "mock_fallback"
    assert result["execution_status"] == "fallback"
    assert "TAVILY_API_KEY" in result["error_traceback"]


def test_tavily_response_is_normalized(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(
        traffic_worker,
        "urlopen",
        lambda request, timeout: FakeResponse({
            "results": [{
                "title": "台北到台中交通",
                "url": "https://example.com/route",
                "content": "搭乘高鐵約 60 分鐘，票價 700 元。",
            }]
        }),
    )

    result = traffic_node(_state())

    traffic = result["traffic_result"]
    assert traffic["source"] == "tavily_search"
    assert traffic["total_transport_time_minutes"] == 120
    assert traffic["total_transport_cost"] == 1400
    assert [segment["direction"] for segment in traffic["segments"]] == ["outbound", "return"]
    assert traffic["references"][0]["title"] == "台北到台中交通"


def test_tavily_insufficient_result_uses_route_estimate(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(
        traffic_worker,
        "urlopen",
        lambda request, timeout: FakeResponse({
            "results": [{
                "title": "交通資訊",
                "url": "https://example.com/info",
                "content": "請在出發前查詢營運單位最新資訊。",
            }]
        }),
    )

    result = traffic_node(_state())

    traffic = result["traffic_result"]
    assert traffic["source"] == "tavily_search"
    assert traffic["total_transport_time_minutes"] == 120
    assert traffic["total_transport_cost"] == 1400
    assert "fallback route estimate" in traffic["source_detail"]


def test_tavily_low_taipei_taichung_hsr_cost_is_corrected(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(
        traffic_worker,
        "urlopen",
        lambda request, timeout: FakeResponse({
            "results": [{
                "title": "高鐵交通資訊",
                "url": "https://example.com/hsr",
                "content": "台北到台中搭乘高鐵約 50 分鐘，票價 90 元。",
            }]
        }),
    )

    traffic = traffic_node(_state())["traffic_result"]

    assert traffic["segments"][0]["estimated_cost"] == 700
    assert traffic["total_transport_cost"] == 1400
    assert "票價由 rule-based sanity check 修正" in traffic["segments"][0]["note"]

    budget_state = {
        **_state(),
        "traffic_result": traffic,
        "transport_result": {},
        "booking_result": {},
        "itinerary_result": {"ticket_cost_total": 0},
        "total_budget": 6000,
        "days": 2,
        "nights": 1,
        "budget_allocation": {
            "hotel_budget": 2400,
            "transport_budget": 1080,
            "food_budget": 1620,
            "activity_budget": 300,
            "buffer_budget": 600,
        },
    }
    budget = budget_node(budget_state)["budget_result"]
    assert budget["breakdown"]["transport"] == 1400
