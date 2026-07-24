import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node


def test_final_response_includes_e2b_system_check_and_limits_issues(monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "0")
    state = {
        "messages": [HumanMessage(content="安排台中行程")],
        "weather_result": {
            "destination": "台中",
            "condition": "晴",
            "rain_probability": 10,
            "temperature": "25-30°C",
            "outdoor_risk": "low",
            "recommendation": "適合戶外活動。",
        },
        "e2b_validation_result": {
            "validation_status": "warning",
            "issues": [
                {"severity": "medium", "message": "問題一"},
                {"severity": "low", "message": "問題二"},
                {"severity": "medium", "message": "問題三"},
                {"severity": "high", "message": "問題四不應顯示"},
            ],
            "recommendation": "請調整行程。",
            "source": "e2b_sandbox",
        },
    }

    result = final_response_node(state)

    answer = result["final_answer"]
    assert "系統檢查：" in answer
    assert "檢查狀態：warning" in answer
    assert "問題一" in answer
    assert "問題三" in answer
    assert "問題四不應顯示" not in answer
    assert "請調整行程" in answer
    assert "e2b_validation_result" not in answer
