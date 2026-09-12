"""子圖狀態隔離與平行 fan-out 的行為驗證。

這個檔案回答一個具體問題：`agents/stage_graph.py` 的子圖包裝到底防住了什麼？

答案是 LangGraph 的 `InvalidUpdateError`。當兩個分支在同一個 superstep 同時寫入
一個沒有 reducer 的欄位（例如 coder 產出的 `generated_code`），LangGraph 不會替你
挑一個贏家，而是直接拋錯。`make_stage_node` 把這類中繼欄位關在各自的子圖裡，父圖
只收得到彼此不同的 result key，因此平行分支天生不會相撞。

test_naive_parallel_stages_collide 先把「問題」釘住，後面兩支再證明包裝解掉了它。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.stage_graph import make_stage_node
from agents.supervisor import route_next
from agents.workers import coder_worker, sandbox_worker
from core.state import AgentState


USER_QUERY = "幫我規劃台中兩天一夜，預算 6000 元"


def _start_node(state: AgentState) -> dict:
    return {"current_task": "start"}


def _build_parent_graph(travel_node, booking_node):
    """start 之後同時 fan-out 到 travel 與 booking 兩個分支。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("start", _start_node)
    workflow.add_node("travel", travel_node)
    workflow.add_node("booking", booking_node)
    workflow.set_entry_point("start")
    workflow.add_edge("start", "travel")
    workflow.add_edge("start", "booking")
    workflow.add_edge("travel", END)
    workflow.add_edge("booking", END)
    return workflow.compile()


# --- 1. 沒有隔離時會發生什麼 -------------------------------------------------
def test_naive_parallel_stages_collide_on_generated_code():
    """兩個分支各自把 coder 產出的程式碼寫進父狀態，LangGraph 會拒絕合併。"""

    def naive_travel(state: AgentState) -> dict:
        return {"generated_code": "print('travel')", "travel_result": {"stage": "travel"}}

    def naive_booking(state: AgentState) -> dict:
        return {"generated_code": "print('booking')", "booking_result": {"stage": "booking"}}

    graph = _build_parent_graph(naive_travel, naive_booking)

    with pytest.raises(InvalidUpdateError) as excinfo:
        graph.invoke({"messages": [HumanMessage(content=USER_QUERY)]})

    assert "generated_code" in str(excinfo.value)


# --- 2. 子圖包裝之後 ---------------------------------------------------------
def _spec_worker(stage_tag: str):
    """符合子圖合約的 worker：產出一份規格交給 coder，而不是自己算出結果。

    這是 2026-07-15 demo-safe 改寫之前所有 domain worker 的形狀，目前 repo 裡
    只有 `agents/workers/schedule_worker.py` 仍維持這個合約。
    """

    def worker(state) -> dict:
        return {
            "messages": [AIMessage(content=f"請查詢 {stage_tag} 相關資料")],
            "next_step": "coder",
        }

    return worker


def _stub_llm_and_sandbox(monkeypatch):
    """讓 coder 與 sandbox 離線可測：程式碼與 stdout 都帶上 stage 標記以便區分分支。"""

    def _tag_of(text: str) -> str:
        return "travel" if "travel" in text else "booking"

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            tag = _tag_of(str(messages[-1].content))
            code = f"print('{{\"stage\": \"{tag}\"}}')"
            return SimpleNamespace(content=f"```python\n{code}\n```")

    def fake_run_python_in_sandbox(code: str):
        return {
            "status": "success",
            "stdout": json.dumps({"stage": _tag_of(code)}),
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(coder_worker, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(coder_worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )


def test_make_stage_node_keeps_intermediate_state_out_of_parent(monkeypatch):
    """單一 stage：父圖只拿得到 result key、摘要訊息與 stage log。"""
    _stub_llm_and_sandbox(monkeypatch)

    stage_node = make_stage_node(_spec_worker("travel"), "travel_result", "travel")
    update = stage_node({"messages": [HumanMessage(content=USER_QUERY)]})

    assert update["travel_result"] == {"stage": "travel"}

    # 子圖內部的中繼欄位一律不得外流到父圖
    for leaked_key in ("generated_code", "sandbox_stdout", "sandbox_stderr", "execution_status"):
        assert leaked_key not in update

    # 但可觀測性要保留：stage log 記得下程式碼長度，供前端與除錯使用
    assert update["stage_logs"][0]["stage"] == "travel"
    assert update["stage_logs"][0]["has_result"] is True
    assert update["stage_logs"][0]["code_chars"] > 0


def test_isolated_stages_fan_out_in_parallel_without_collision(monkeypatch):
    """同一個 superstep 跑兩個 stage：兩份結果都要在，且不得重演 InvalidUpdateError。"""
    _stub_llm_and_sandbox(monkeypatch)

    graph = _build_parent_graph(
        make_stage_node(_spec_worker("travel"), "travel_result", "travel"),
        make_stage_node(_spec_worker("booking"), "booking_result", "booking"),
    )

    result = graph.invoke({"messages": [HumanMessage(content=USER_QUERY)]})

    assert result["travel_result"] == {"stage": "travel"}
    assert result["booking_result"] == {"stage": "booking"}
    assert "generated_code" not in result

    # messages 與 stage_logs 掛了 operator.add，兩個分支的產出應該是合併而非互相覆蓋
    assert {log["stage"] for log in result["stage_logs"]} == {"travel", "booking"}


# --- 3. 確定性調度器 ---------------------------------------------------------
def test_route_next_returns_list_for_parallel_group():
    """travel 與 booking 同屬一個平行組，兩者都未完成時應一次回傳 list。"""
    done_logs = [{"stage": "budget"}, {"stage": "weather"}]

    assert route_next({"stage_logs": []}) == "budget"
    assert route_next({"stage_logs": [{"stage": "budget"}]}) == "weather"
    assert route_next({"stage_logs": done_logs}) == ["travel", "booking"]

    # 平行組只完成一半時，只補跑缺的那一個
    assert route_next({"stage_logs": [*done_logs, {"stage": "travel"}]}) == ["booking"]

    # 進度以「有沒有跑過」判斷，因此失敗（沒有 result）的 stage 也算數，流程不會卡死
    all_done = [*done_logs, {"stage": "travel"}, {"stage": "booking"}, {"stage": "traffic"}]
    assert route_next({"stage_logs": all_done}) == "scheduler"
    assert route_next({"stage_logs": [*all_done, {"stage": "scheduler"}]}) == "FINISH"


# --- 4. 兩種 worker 合約 -----------------------------------------------------
def test_self_producing_worker_skips_the_coder_chain(monkeypatch):
    """新合約：worker 已自行產出結果時，子圖不應再進 coder，也不該因路由而崩潰。

    2026-07-15 的 demo-safe 改寫把 domain worker 從「產規格」改成「自行產出結果」，
    回傳的 `next_step` 變成主線 pipeline 的下一棒（例如 weather 回傳 "spot"）。
    舊版路由只列舉 coder / final_response / FINISH，遇到 "spot" 會直接 KeyError。
    """

    def coder_must_not_run(state):  # pragma: no cover - 只用來確認沒被呼叫
        raise AssertionError("worker 已產出結果時不該進入 coder")

    monkeypatch.setattr("agents.stage_graph.coder_node", coder_must_not_run)

    def self_producing_worker(state) -> dict:
        return {
            "weather_result": {"destination": "台中", "source": "mock_fallback"},
            "execution_status": "fallback",
            "next_step": "spot",
        }

    stage_node = make_stage_node(self_producing_worker, "weather_result", "weather")
    update = stage_node({"messages": [HumanMessage(content=USER_QUERY)]})

    assert update["weather_result"]["destination"] == "台中"
    assert update["stage_logs"][0]["code_chars"] == 0
    assert "generated_code" not in update
