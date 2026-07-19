import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import traffic_worker
from agents.workers.traffic_worker import traffic_node


VALID_TRAFFIC = {
    "origin": "台北車站",
    "destination": "台中",
    "segments": [
        {
            "from": "台北車站",
            "to": "台中車站",
            "mode": "高鐵",
            "duration_minutes": 60,
            "estimated_cost": 700,
            "note": "此為規劃估計，請查證實際班次與票價。",
        },
        {
            "from": "台中車站",
            "to": "審計新村",
            "mode": "公車",
            "duration_minutes": 30,
            "estimated_cost": 50,
            "note": "此為規劃估計。",
        },
    ],
    "total_transport_time_minutes": 999,
    "total_transport_cost": 9999,
    "feasibility": "good",
    "warning": "此為行程規劃估計，不是真實即時交通資料。",
}


def _state():
    return {
        "trip_request": {
            "origin": "台北",
            "departure_station": "台北車站",
            "destination": "台中",
            "preference": "不要太趕",
        },
        "spot_result": {"spots": [{"name": "審計新村"}]},
        "itinerary_result": {},
    }


def test_live_traffic_success_uses_llm_source(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps(VALID_TRAFFIC, ensure_ascii=False))

    monkeypatch.setenv("USE_LIVE_TRAFFIC", "true")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(traffic_worker, "ChatOpenAI", FakeChatOpenAI)

    result = traffic_node(_state())

    assert result["execution_status"] == "success"
    assert result["traffic_result"]["source"] == "llm"
    assert result["traffic_result"]["model"] == "openai/gpt-4o-mini"
    assert result["traffic_result"]["total_transport_time_minutes"] == 90
    assert result["traffic_result"]["total_transport_cost"] == 750
    assert result["next_step"] == "travel"


def test_live_traffic_invalid_json_falls_back(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            return SimpleNamespace(content="invalid traffic JSON")

    monkeypatch.setenv("USE_LIVE_TRAFFIC", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(traffic_worker, "ChatOpenAI", FakeChatOpenAI)

    result = traffic_node(_state())

    assert result["execution_status"] == "fallback"
    assert result["traffic_result"]["source"] == "mock_fallback"
    assert result["traffic_result"]["source_detail"] == (
        "Live traffic generation unavailable or failed; using mock traffic result."
    )
    assert result["error_traceback"]


def test_live_traffic_missing_field_falls_back(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps({"destination": "台中"}, ensure_ascii=False))

    monkeypatch.setenv("USE_LIVE_TRAFFIC", "on")
    monkeypatch.setattr(traffic_worker, "ChatOpenAI", FakeChatOpenAI)

    result = traffic_node(_state())

    assert result["traffic_result"]["source"] == "mock_fallback"
    assert "missing required fields" in result["error_traceback"]
