import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import spot_worker
from agents.workers.spot_worker import spot_node


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
        "destination": "台中",
        "days": 2,
        "preference": "不要太趕、戶外景點",
        "trip_request": {"destination": "台中", "days": 2, "preference": "不要太趕、戶外景點"},
        "weather_result": {"outdoor_risk": "low"},
    }


def _configure_tavily(monkeypatch):
    monkeypatch.setenv("USE_LIVE_SPOT", "1")
    monkeypatch.setenv("SPOT_PROVIDER", "tavily")


def _mock_results():
    return {
        "results": [
            {
                "title": "台中 審計新村｜戶外散步景點",
                "url": "https://example.com/a",
                "content": "台中審計新村適合戶外散步，建議停留 80 分鐘，免費參觀。",
            },
            {
                "title": "台中 審計新村｜重複推薦",
                "url": "https://example.com/duplicate",
                "content": "台中戶外景點審計新村。",
            },
            {
                "title": "台中 高美濕地｜自然景觀",
                "url": "https://example.com/b",
                "content": "台中高美濕地是自然景觀與夕陽景點。",
            },
            {
                "title": "台中 國家歌劇院｜文化景點",
                "url": "https://example.com/c",
                "content": "台中國家歌劇院文化參觀，門票費用 300 元。",
            },
            {
                "title": "台中飯店訂房廣告",
                "url": "https://example.com/ad",
                "content": "台中住宿飯店優惠。",
            },
        ]
    }


def test_tavily_spots_are_normalized_deduplicated_and_filtered(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(
        spot_worker,
        "urlopen",
        lambda request, timeout: FakeResponse(_mock_results()),
    )

    result = spot_node(_state())["spot_result"]

    assert result["source"] == "tavily_search"
    assert len(result["spots"]) == 3
    assert [spot["name"] for spot in result["spots"]].count("審計新村") == 1
    assert all("飯店" not in spot["name"] for spot in result["spots"])
    assert result["ticket_cost_total"] == 300
    high_mei = next(spot for spot in result["spots"] if spot["name"] == "高美濕地")
    assert high_mei["type"] == "nature"
    assert high_mei["duration_minutes"] == 120
    assert high_mei["estimated_cost"] == 0


def test_insufficient_tavily_spots_are_supplemented_with_mock(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(
        spot_worker,
        "urlopen",
        lambda request, timeout: FakeResponse({"results": _mock_results()["results"][:1]}),
    )

    result = spot_node(_state())["spot_result"]

    assert result["source"] == "tavily_search_with_mock_fallback"
    assert len(result["spots"]) >= 3
    assert any(spot["source_title"] == "mock_spot_data" for spot in result["spots"])


def test_missing_tavily_key_falls_back_without_crashing(monkeypatch):
    _configure_tavily(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = spot_node(_state())

    assert result["spot_result"]["source"] == "mock_spot_data"
    assert result["execution_status"] == "fallback"
    assert result["next_step"] == "booking"
    assert "TAVILY_API_KEY" in result["error_traceback"]
