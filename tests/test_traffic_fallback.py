import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.traffic_worker import build_mock_traffic_result, traffic_node


def test_build_mock_traffic_result_contains_required_fields():
    result = build_mock_traffic_result(
        {
            "departure_station": "台北車站",
            "destination": "台中",
        }
    )

    assert result["origin"] == "台北車站"
    assert result["destination"] == "台中"
    assert result["segments"]
    assert result["total_transport_time_minutes"] == 120
    assert result["total_transport_cost"] == 750
    assert result["feasibility"] == "good"
    assert result["warning"]


def test_traffic_node_fallback_does_not_need_api_key(monkeypatch):
    monkeypatch.setenv("USE_LIVE_TRAFFIC", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = traffic_node({"departure_station": "台北車站", "destination": "台中"})

    assert result["execution_status"] == "fallback"
    assert result["traffic_result"]["segments"]
    assert result["traffic_result"]["total_transport_cost"] == 750
    assert result["next_step"] == "travel"
