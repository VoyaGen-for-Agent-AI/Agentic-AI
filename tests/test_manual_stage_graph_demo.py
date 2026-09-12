"""保護 `scripts/manual_stage_graph_demo.py`：這支腳本是子圖 + supervisor 架構唯一的
端到端執行入口，CI 只跑 tests/，沒有這個檔案它壞掉不會有人發現。

第一支測試會真的把整張圖跑一遍（mock 模式、不需任何金鑰），因此它同時也是這套架構
的端到端回歸測試，而不只是在測印字。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import manual_stage_graph_demo as demo


def _offline(monkeypatch):
    """關掉所有 live 模式並移除憑證，讓每個 stage 走 mock，執行結果可重現。"""
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_SPOT", "USE_LIVE_TRAFFIC",
                 "USE_LIVE_ITINERARY", "USE_LIVE_BOOKING"):
        monkeypatch.setenv(name, "0")
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "E2B_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("STAGE_DEMO_DELAY_SECONDS", "0")
    monkeypatch.setattr(demo, "_timeline", [])


def test_build_graph_completes_every_stage_without_credentials(monkeypatch):
    """六個 stage 都要跑完，且子圖的中繼欄位一個都不能外流到父狀態。"""
    _offline(monkeypatch)
    from langchain_core.messages import HumanMessage

    result = demo.build_graph().invoke(
        {"messages": [HumanMessage(content="台中兩天一夜，兩人，預算 6000 元")]}
    )

    completed = {log["stage"] for log in result["stage_logs"]}
    assert completed == {name for name, _, _ in demo.STAGES}

    # scheduler 走舊合約需要 LLM，無憑證時應降級成沒有結果，但不得中斷流程
    assert result["weather_result"]
    assert result["travel_result"]
    assert result["booking_result"]
    assert result["traffic_result"]
    assert result["budget_result"]

    for internal_key in demo.INTERNAL_KEYS:
        assert internal_key not in result

    assert result["final_answer"]


def test_stage_order_matches_supervisor(monkeypatch):
    """腳本的 STAGES 必須涵蓋 supervisor 的 STAGE_ORDER，否則 route_next 會無限迴圈。"""
    from agents.supervisor import STAGE_ORDER

    expected = set()
    for step in STAGE_ORDER:
        expected.update(step if isinstance(step, tuple) else (step,))

    assert {name for name, _, _ in demo.STAGES} == expected


def test_report_flags_leaked_internal_state(capsys):
    demo._timeline = [
        {"stage": "travel", "thread": "T1", "start": 0.0, "end": 1.0},
        {"stage": "booking", "thread": "T2", "start": 0.5, "end": 1.5},
    ]

    demo._report({
        "stage_logs": [{"stage": "travel", "status": "success", "has_result": True, "code_chars": 0}],
        "travel_result": {"ok": 1},
        "generated_code": "print('leaked')",
        "final_answer": "完成",
    })

    output = capsys.readouterr().out
    assert "generated_code" in output
    assert "隔離失效" in output
    assert "travel / booking 時間重疊：True" in output


def test_main_runs_end_to_end_and_prints_every_section(monkeypatch, capsys):
    _offline(monkeypatch)
    # main() 會 load_dotenv()，本機 .env 會把憑證塞回來並觸發真實網路呼叫
    monkeypatch.setattr(demo, "load_dotenv", lambda *args, **kwargs: False)

    assert demo.main() == 0

    output = capsys.readouterr().out
    assert "各 stage 執行結果" in output
    assert "平行 fan-out 驗證" in output
    assert "子圖狀態隔離驗證" in output
    assert "外流的子圖中繼欄位：無" in output
