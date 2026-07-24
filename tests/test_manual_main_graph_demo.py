import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import manual_main_graph_demo


def _fake_graph_result():
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
        def invoke(self, initial_state, config=None):
            captured["query"] = initial_state["messages"][0].content
            captured["config"] = config
            return _fake_graph_result()

    monkeypatch.setattr("builtins.input", lambda prompt: "安排高雄一日遊")
    monkeypatch.setattr(manual_main_graph_demo, "app_graph", FakeGraph())
    monkeypatch.setattr(manual_main_graph_demo, "get_langfuse_callbacks", lambda: [])
    monkeypatch.setenv("DEMO_SHOW_DEBUG", "0")
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "0")
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_TRAFFIC", "USE_LIVE_ITINERARY"):
        monkeypatch.setenv(name, "0")

    assert manual_main_graph_demo.main() == 0
    assert captured["query"] == "安排高雄一日遊"
    output = capsys.readouterr().out
    assert "user_query: 安排高雄一日遊" in output
    assert "Observability disabled" in output
    assert "Weather provider:" not in output
    assert "weather_result source:" not in output
    assert "spot_result source:" not in output
    assert "trip_request:" not in output
    assert "spot_result:" not in output
    assert "rule_based_parser" not in output
    assert captured["config"]["callbacks"] == []


def test_main_passes_langfuse_callbacks_metadata_and_tags(monkeypatch, capsys):
    captured = {}
    fake_callback = object()

    class FakeGraph:
        def invoke(self, initial_state, config=None):
            captured["query"] = initial_state["messages"][0].content
            captured["config"] = config
            return _fake_graph_result()

    monkeypatch.setattr("builtins.input", lambda prompt: "安排台中兩天一夜")
    monkeypatch.setattr(manual_main_graph_demo, "app_graph", FakeGraph())
    monkeypatch.setattr(
        manual_main_graph_demo,
        "get_langfuse_callbacks",
        lambda: [fake_callback],
    )
    monkeypatch.setenv("WEATHER_PROVIDER", "openweather")
    monkeypatch.setenv("TRAFFIC_PROVIDER", "tavily")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("DEMO_SHOW_DEBUG", "0")
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "0")
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_TRAFFIC", "USE_LIVE_ITINERARY"):
        monkeypatch.setenv(name, "0")

    assert manual_main_graph_demo.main() == 0

    config = captured["config"]
    assert config["callbacks"] == [fake_callback]
    assert config["metadata"] == {
        "demo": "manual_main_graph_demo",
        "user_query": "安排台中兩天一夜",
        "weather_provider": "openweather",
        "traffic_provider": "tavily",
        "llm_model": "openai/gpt-4o-mini",
    }
    assert config["tags"] == ["demo", "main_graph", "travel_agent"]
    assert "Observability enabled" in capsys.readouterr().out


def test_debug_mode_prints_provider_sources_and_raw_results(monkeypatch, capsys):
    class FakeGraph:
        def invoke(self, initial_state, config=None):
            return _fake_graph_result()

    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(manual_main_graph_demo, "app_graph", FakeGraph())
    monkeypatch.setattr(manual_main_graph_demo, "get_langfuse_callbacks", lambda: [])
    monkeypatch.setenv("DEMO_SHOW_DEBUG", "1")
    monkeypatch.setenv("WEATHER_PROVIDER", "openweather")
    monkeypatch.setenv("TRAFFIC_PROVIDER", "tavily")
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_TRAFFIC", "USE_LIVE_ITINERARY"):
        monkeypatch.setenv(name, "0")

    assert manual_main_graph_demo.main() == 0

    output = capsys.readouterr().out
    assert "Weather provider: openweather" in output
    assert "Traffic provider: tavily" in output
    assert "Spot provider:" in output
    assert "weather_result source: mock_fallback" in output
    assert "spot_result source: mock_spot_data" in output
    assert "[trip_request] source: rule_based_parser" in output
    assert "trip_request:" in output
