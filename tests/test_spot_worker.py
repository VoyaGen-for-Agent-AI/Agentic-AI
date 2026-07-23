import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.spot_worker import spot_node


def make_state(**overrides):
    state = {
        "destination": "台中",
        "days": 2,
        "preference": "不要太趕、戶外景點",
        "weather_result": {"outdoor_risk": "low"},
    }
    state.update(overrides)
    return state


def test_spot_node_generates_spot_result(monkeypatch):
    monkeypatch.setenv("USE_LIVE_SPOT", "0")
    result = spot_node(make_state())

    assert result["current_task"] == "spot"
    assert result["next_step"] == "booking"
    assert result["spot_result"]["destination"] == "台中"
    assert result["spot_result"]["spots"]
    assert result["spot_result"]["ticket_cost_total"] >= 0
    assert {"name", "type", "duration_minutes", "estimated_cost", "reason"} <= set(
        result["spot_result"]["spots"][0]
    )


def test_spot_node_adjusts_for_high_outdoor_risk(monkeypatch):
    monkeypatch.setenv("USE_LIVE_SPOT", "0")
    result = spot_node(make_state(weather_result={"outdoor_risk": "high"}))

    first_types = [spot["type"] for spot in result["spot_result"]["spots"][:2]]
    assert any(spot_type in {"indoor", "semi_indoor"} for spot_type in first_types)
    assert "室內" in result["spot_result"]["recommendation"]
