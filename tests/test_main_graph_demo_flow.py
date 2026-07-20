import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app_graph


DEMO_PROMPT = "我想在 7/18 到 7/19 從台北車站出發去台中兩天一夜，一人總預算 6000 元，希望行程不要太趕，想安排戶外景點，也請幫我找交通方便的住宿，最後估算整趟旅程的總花費。"


def test_main_graph_demo_flow_without_external_keys(monkeypatch):
    monkeypatch.setenv("USE_LIVE_WEATHER", "0")
    monkeypatch.setenv("USE_LIVE_TRAFFIC", "0")
    monkeypatch.setenv("USE_LIVE_ITINERARY", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    result = app_graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    assert result["trip_request"]
    assert result["weather_result"]
    assert result["spot_result"]
    assert result["booking_result"]
    assert result["traffic_result"]
    assert result["itinerary_result"] or result["travel_result"]
    assert result["budget_result"]
    assert result["final_answer"]

    final_answer = result["final_answer"]
    for keyword in ("台中", "天氣", "景點", "住宿", "交通", "行程", "預算"):
        assert keyword in final_answer
