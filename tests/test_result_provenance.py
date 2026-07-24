import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app_graph


DEMO_PROMPT = (
    "我想這週末(7/18~7/19)從台北(台北車站出發)去台中兩天一夜，"
    "一人總預算 6000 元，希望行程不要太趕，想去戶外景點，也幫我找住宿"
)


def test_main_graph_results_include_provenance(monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "1")
    monkeypatch.setenv("USE_LIVE_WEATHER", "0")
    monkeypatch.setenv("USE_LIVE_TRAFFIC", "0")
    monkeypatch.setenv("USE_LIVE_ITINERARY", "0")
    monkeypatch.setenv("USE_LIVE_SPOT", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    result = app_graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    assert result["trip_request"]["source"] == "rule_based_parser"
    assert result["weather_result"]["source"] == "mock_fallback"
    assert result["spot_result"]["source"] == "mock_spot_data"
    assert result["booking_result"]["source"] == "mock_hotel_data"
    assert result["traffic_result"]["source"] == "mock_fallback"
    assert result["itinerary_result"]["source"] == "mock_fallback"
    assert result["budget_result"]["source"] == "rule_based"
    assert "資料來源摘要" in result["final_answer"]
