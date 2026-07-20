import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import weather_worker
from agents.workers.weather_worker import weather_node


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _state(destination="台中"):
    return {
        "destination": destination,
        "start_date": "7/18",
        "end_date": "7/19",
        "trip_request": {"destination": destination, "start_date": "7/18", "end_date": "7/19"},
    }


def _configure_openweather(monkeypatch):
    monkeypatch.setenv("USE_LIVE_WEATHER", "1")
    monkeypatch.setenv("WEATHER_PROVIDER", "openweather")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_openweather_missing_key_falls_back(monkeypatch):
    _configure_openweather(monkeypatch)
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)

    result = weather_node(_state())

    assert result["weather_result"]["source"] == "mock_fallback"
    assert result["execution_status"] == "fallback"
    assert "OPENWEATHER_API_KEY" in result["error_traceback"]


def test_openweather_unknown_coordinates_falls_back(monkeypatch):
    _configure_openweather(monkeypatch)
    monkeypatch.setenv("OPENWEATHER_API_KEY", "fake-key")

    result = weather_node(_state("澎湖"))

    assert result["weather_result"]["source"] == "mock_fallback"
    assert "unknown coordinates" in result["error_traceback"]


def test_openweather_response_is_normalized(monkeypatch):
    _configure_openweather(monkeypatch)
    monkeypatch.setenv("OPENWEATHER_API_KEY", "fake-key")
    first_day = date.today() + timedelta(days=1)
    second_day = first_day + timedelta(days=1)
    state = _state()
    state.update(start_date=first_day.isoformat(), end_date=second_day.isoformat())
    state["trip_request"].update(start_date=first_day.isoformat(), end_date=second_day.isoformat())
    forecast_entries = [
        {
            "dt_txt": f"{forecast_day.isoformat()} 12:00:00",
            "weather": [{"id": 500, "description": "小雨"}],
            "main": {"temp_min": 26.2, "temp_max": 31.7},
            "pop": 0.8,
        }
        for forecast_day in (first_day, second_day)
    ]
    monkeypatch.setattr(weather_worker, "urlopen", lambda request, timeout: FakeResponse({"list": forecast_entries}))

    result = weather_node(state)

    weather = result["weather_result"]
    assert weather["source"] == "api_openweather_forecast"
    assert weather["destination"] == "台中"
    assert weather["temperature"] == "26-32°C"
    assert weather["outdoor_risk"] == "high"
    assert len(weather["forecast_days"]) == 2


def test_out_of_forecast_range_uses_current_weather(monkeypatch):
    _configure_openweather(monkeypatch)
    monkeypatch.setenv("OPENWEATHER_API_KEY", "fake-key")

    def fake_urlopen(request, timeout):
        if "/forecast?" in request:
            return FakeResponse({"list": []})
        return FakeResponse({
            "weather": [{"id": 800, "description": "晴朗"}],
            "main": {"temp_min": 25, "temp_max": 30},
        })

    monkeypatch.setattr(weather_worker, "urlopen", fake_urlopen)
    result = weather_node({
        "destination": "台中",
        "start_date": "2099-07-18",
        "end_date": "2099-07-19",
        "trip_request": {"destination": "台中", "start_date": "2099-07-18", "end_date": "2099-07-19"},
    })

    weather = result["weather_result"]
    assert weather["source"] == "api_openweather_current"
    assert weather["forecast_days"] == []
    assert "旅遊日期超出 forecast range" in weather["recommendation"]
    assert result["execution_status"] == "success"
