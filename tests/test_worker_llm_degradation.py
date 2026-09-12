"""回歸測試：缺少 API 金鑰時，需要 LLM 的 worker 必須降級而不是讓整張圖崩潰。

`ChatOpenAI` 的建構本身就會驗證憑證，沒有金鑰時直接拋 `OpenAIError`。這兩個 node
原本把建構寫在 try 區塊之外，因此無金鑰環境下不是「這個 stage 沒有結果」，而是
整張 LangGraph 直接中斷。這裡把修正後的行為釘住，避免日後又被移回 try 外面。
"""

import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.coder_worker import coder_node
from agents.workers.schedule_worker import schedule_node


def _drop_llm_credentials(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_coder_node_degrades_when_credentials_are_missing(monkeypatch):
    _drop_llm_credentials(monkeypatch)

    update = coder_node({"messages": [HumanMessage(content="請查詢台中天氣")]})

    assert update["next_step"] == "FINISH"
    assert update["execution_status"] == "error"
    assert update["error_traceback"]
    assert "generated_code" not in update


def test_schedule_node_degrades_when_credentials_are_missing(monkeypatch):
    _drop_llm_credentials(monkeypatch)

    update = schedule_node({"messages": [HumanMessage(content="規劃台中兩天一夜")]})

    assert update["next_step"] == "FINISH"
    assert "messages" not in update
