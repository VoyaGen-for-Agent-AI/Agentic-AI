import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node


def test_tavily_spots_render_cleanly_without_sources_or_references(monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_SOURCES", "0")
    result = final_response_node({
        "messages": [HumanMessage(content="台中景點")],
        "spot_result": {
            "destination": "台中",
            "spots": [
                {
                    "name": "高美濕地",
                    "type": "nature",
                    "area": "清水",
                    "estimated_cost": 0,
                    "duration_minutes": 120,
                    "reason": "適合欣賞夕陽與自然景觀。",
                    "source_title": "台中景點推薦",
                }
            ],
            "ticket_cost_total": 0,
            "recommendation": "出發前確認開放資訊。",
            "source": "tavily_search",
            "references": [
                {"title": "台中景點推薦", "url": "https://example.com/a/very/long/url", "snippet": "raw snippet"}
            ],
        },
    })

    answer = result["final_answer"]
    assert "高美濕地（nature）：費用約 0 元，建議停留 120 分鐘" in answer
    assert "推薦原因：適合欣賞夕陽與自然景觀" in answer
    assert "資料來源摘要" not in answer
    assert "tavily_search" not in answer
    assert "https://" not in answer
    assert "raw snippet" not in answer
