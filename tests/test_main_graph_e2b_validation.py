import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app_graph


def test_main_graph_contains_e2b_validation_between_travel_and_budget():
    edges = {(edge.source, edge.target) for edge in app_graph.get_graph().edges}

    assert ("travel", "e2b_validation") in edges
    assert ("e2b_validation", "budget") in edges
    assert ("travel", "budget") not in edges


def test_main_graph_skips_e2b_without_key_and_still_finishes(monkeypatch):
    monkeypatch.setenv("USE_LIVE_WEATHER", "0")
    monkeypatch.setenv("USE_LIVE_TRAFFIC", "0")
    monkeypatch.setenv("USE_LIVE_ITINERARY", "0")
    monkeypatch.setenv("USE_LIVE_SPOT", "0")
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "0")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = app_graph.invoke({
        "messages": [HumanMessage(content="請安排台北到台中兩天一夜，預算 6000，需要住宿")]
    })

    assert result["e2b_validation_result"]["source"] == "e2b_skipped"
    assert result["budget_result"]["source"] == "rule_based"
    assert result["final_answer"]
    assert "系統檢查" in result["final_answer"]
