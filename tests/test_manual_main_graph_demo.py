import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import manual_main_graph_demo


def test_get_user_query_uses_default_for_empty_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    result = manual_main_graph_demo.get_user_query("default query")

    assert result == "default query"


def test_get_user_query_uses_custom_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "  自訂台南行程  ")

    result = manual_main_graph_demo.get_user_query("default query")

    assert result == "自訂台南行程"


def test_main_invokes_app_graph_with_selected_query(monkeypatch, capsys):
    captured = {}

    class FakeGraph:
        def invoke(self, initial_state):
            captured["query"] = initial_state["messages"][0].content
            return {
                "trip_request": {"source": "rule_based_parser"},
                "weather_result": {"source": "mock_fallback"},
                "spot_result": {"source": "mock_spot_data"},
                "booking_result": {"source": "mock_hotel_data"},
                "traffic_result": {"source": "mock_fallback"},
                "itinerary_result": {"source": "mock_fallback"},
                "travel_result": {},
                "budget_result": {"source": "rule_based"},
                "final_answer": "完成",
            }

    monkeypatch.setattr("builtins.input", lambda prompt: "安排高雄一日遊")
    monkeypatch.setattr(manual_main_graph_demo, "app_graph", FakeGraph())
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_TRAFFIC", "USE_LIVE_ITINERARY"):
        monkeypatch.setenv(name, "0")

    assert manual_main_graph_demo.main() == 0
    assert captured["query"] == "安排高雄一日遊"
    assert "user_query: 安排高雄一日遊" in capsys.readouterr().out
