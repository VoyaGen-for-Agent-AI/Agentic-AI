import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import e2b_validation_worker
from agents.workers.e2b_validation_worker import build_validation_code, e2b_validation_node


def make_state():
    return {
        "trip_request": {"days": 2, "total_budget": 6000},
        "traffic_result": {
            "segments": [
                {"from": "台北車站", "to": "台中車站", "mode": "高鐵", "direction": "outbound", "estimated_cost": 700},
                {"from": "台中車站", "to": "台北車站", "mode": "高鐵", "direction": "return", "estimated_cost": 700},
            ],
            "total_transport_cost": 1400,
        },
        "itinerary_result": {
            "style": "relaxed",
            "schedule": [{"day": 1, "items": []}, {"day": 2, "items": []}],
            "ticket_cost_total": 0,
        },
        "booking_result": {"recommended_hotel": {"total_price": 2100}},
        "budget_allocation": {"hotel_budget": 2400},
    }


def test_build_validation_code_produces_valid_python():
    code = build_validation_code(make_state())

    assert "has_round_trip_transport" in code
    assert "schedule_not_too_rushed" in code
    compile(code, "<e2b-validation>", "exec")


def test_missing_e2b_key_skips_and_continues_to_budget(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    result = e2b_validation_node(make_state())

    assert result["e2b_validation_result"]["validation_status"] == "skipped"
    assert result["e2b_validation_result"]["source"] == "e2b_skipped"
    assert result["execution_status"] == "skipped"
    assert result["next_step"] == "budget"


def test_valid_sandbox_stdout_is_parsed(monkeypatch):
    payload = {
        "validation_status": "passed",
        "issues": [],
        "checks": {"has_round_trip_transport": True},
        "recommendation": "ok",
        "source": "e2b_sandbox",
    }
    monkeypatch.setenv("E2B_API_KEY", "fake-key")
    monkeypatch.setattr(
        e2b_validation_worker.sandbox_runner,
        "run_python_in_sandbox",
        lambda code: {"status": "success", "stdout": json.dumps(payload), "stderr": "", "error": None},
    )

    result = e2b_validation_node(make_state())

    assert result["e2b_validation_result"]["source"] == "e2b_sandbox"
    assert result["e2b_validation_result"]["validation_status"] == "passed"
    assert result["next_step"] == "budget"


def test_invalid_sandbox_stdout_returns_failed_result(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "fake-key")
    monkeypatch.setattr(
        e2b_validation_worker.sandbox_runner,
        "run_python_in_sandbox",
        lambda code: {"status": "success", "stdout": "not json", "stderr": "", "error": None},
    )

    result = e2b_validation_node(make_state())

    assert result["e2b_validation_result"]["validation_status"] == "failed"
    assert result["e2b_validation_result"]["source"] == "e2b_sandbox"
    assert result["execution_status"] == "error"
    assert result["next_step"] == "budget"
