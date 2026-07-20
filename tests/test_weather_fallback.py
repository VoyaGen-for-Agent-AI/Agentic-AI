import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.weather_worker import build_mock_weather_result, weather_node


def test_build_mock_weather_result_contains_required_fields():
    result = build_mock_weather_result({"destination": "台中"})

    assert result["destination"] == "台中"
    assert result["condition"]
    assert result["rain_probability"] >= 0
    assert result["temperature"]
    assert result["outdoor_risk"]
    assert result["recommendation"]


def test_weather_node_fallback_does_not_need_api_key(monkeypatch):
    monkeypatch.setenv("USE_LIVE_WEATHER", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = weather_node({"destination": "台中"})

    assert result["execution_status"] == "fallback"
    assert result["weather_result"]["condition"]
    assert result["weather_result"]["outdoor_risk"] == "low"
    assert result["next_step"] == "spot"
