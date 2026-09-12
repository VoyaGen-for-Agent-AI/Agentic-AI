"""demo_run.py 的回歸測試。

這支腳本先前從 main.py 匯入已被移除的 `langfuse_handler`，一執行就 ImportError，
但沒有任何測試覆蓋到它。這裡用假的 app_graph 驗證整條呼叫路徑能走完，
確保 main.py 的公開介面再次改名時會被 CI 擋下來。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.observability as observability
import main as main_module
from scripts import demo_run


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def invoke(self, payload, config=None):
        self.calls.append((payload, config))
        return {
            "stage_logs": [{"stage": "weather", "status": "fallback", "has_result": True}],
            "budget_tier": "適中",
            "final_answer": "假的最終回覆",
        }


def test_demo_run_main_completes_without_real_graph(monkeypatch, capsys):
    fake_graph = _FakeGraph()
    monkeypatch.setattr(main_module, "app_graph", fake_graph)
    monkeypatch.setattr(observability, "get_langfuse_callbacks", lambda: [])

    exit_code = demo_run.main()

    assert exit_code == 0
    assert len(fake_graph.calls) == 1

    payload, config = fake_graph.calls[0]
    assert payload["messages"][0].content == demo_run.DEMO_PROMPT
    assert config == {"callbacks": []}

    output = capsys.readouterr().out
    assert "假的最終回覆" in output
    assert "適中" in output


def test_demo_run_falls_back_to_last_message_when_no_final_answer(monkeypatch, capsys):
    class _NoFinalAnswerGraph(_FakeGraph):
        def invoke(self, payload, config=None):
            super().invoke(payload, config)

            class _Message:
                content = "來自 messages 的回覆"

            return {"stage_logs": [], "budget_tier": "", "messages": [_Message()]}

    monkeypatch.setattr(main_module, "app_graph", _NoFinalAnswerGraph())
    monkeypatch.setattr(observability, "get_langfuse_callbacks", lambda: [])

    assert demo_run.main() == 0
    assert "來自 messages 的回覆" in capsys.readouterr().out


def test_missing_helper_accepts_any_of_several_equivalent_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert demo_run._missing("OPENROUTER_API_KEY / OPENAI_API_KEY") is True

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert demo_run._missing("OPENROUTER_API_KEY / OPENAI_API_KEY") is False
