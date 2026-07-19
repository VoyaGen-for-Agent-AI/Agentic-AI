import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import weather_worker
from agents.workers.weather_worker import weather_node


VALID_WEATHER = {
    "destination": "台中",
    "date_range": "7/18 ~ 7/19",
    "condition": "規劃估計：多雲，午後可能有短暫陣雨",
    "rain_probability": 30,
    "temperature": "26-32°C",
    "outdoor_risk": "medium",
    "recommendation": "此為行程規劃估計，出發前請查證官方預報。",
}


def _state():
    return {
        "trip_request": {
            "destination": "台中",
            "start_date": "7/18",
            "end_date": "7/19",
            "preference": "戶外景點",
        }
    }


def test_live_weather_success_uses_llm_source(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps(VALID_WEATHER, ensure_ascii=False))

    monkeypatch.setenv("USE_LIVE_WEATHER", "yes")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(weather_worker, "ChatOpenAI", FakeChatOpenAI)

    result = weather_node(_state())

    assert result["execution_status"] == "success"
    assert result["weather_result"]["source"] == "llm"
    assert result["weather_result"]["model"] == "openai/gpt-4o-mini"
    assert result["next_step"] == "spot"


def test_live_weather_invalid_json_falls_back(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            return SimpleNamespace(content="invalid weather JSON")

    monkeypatch.setenv("USE_LIVE_WEATHER", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(weather_worker, "ChatOpenAI", FakeChatOpenAI)

    result = weather_node(_state())

    assert result["execution_status"] == "fallback"
    assert result["weather_result"]["source"] == "mock_fallback"
    assert result["weather_result"]["source_detail"] == (
        "Live weather generation unavailable or failed; using mock weather result."
    )
    assert result["error_traceback"]


def test_live_weather_missing_field_falls_back(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps({"destination": "台中"}, ensure_ascii=False))

    monkeypatch.setenv("USE_LIVE_WEATHER", "on")
    monkeypatch.setattr(weather_worker, "ChatOpenAI", FakeChatOpenAI)

    result = weather_node(_state())

    assert result["weather_result"]["source"] == "mock_fallback"
    assert "missing required fields" in result["error_traceback"]
