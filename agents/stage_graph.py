"""Stage sub-graph factory.

每個 stage（budget / weather / travel / booking / traffic / scheduler）內部都是
`worker -> coder -> e2b_sandbox -> parser` 這條既有的執行鏈。我們把它包成一個
獨立的 LangGraph 子圖（sub-graph），並用一個 wrapper node 對外只回傳「該 stage 的
result key」與一則摘要訊息。

這樣做的關鍵好處：
- 子圖內部的中繼欄位（generated_code / sandbox_stdout / execution_status ...）
  完全留在子圖裡，不會冒泡到父圖，因此 travel 與 booking 兩個 stage 平行執行時
  不會互相覆蓋狀態（State overwrite）。
- 父圖只看到 travel_result / booking_result 這類不同的 key，加上用 operator.add
  合併的 messages / stage_logs，天生就是平行安全的。
"""

import json
import re
from typing import Any, Callable, Sequence, TypedDict, Annotated
import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from core.state import AgentState
from agents.workers.coder_worker import coder_node
from agents.workers.sandbox_worker import sandbox_node
from agents.workers.parser_worker import parser_node


# --- 子圖專用的隔離狀態 ---------------------------------------------------
class StageState(TypedDict, total=False):
    # worker 讀 messages[0]（乾淨的使用者需求）、coder 讀 messages[-1]（worker 產出的規格）
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # 告訴 parser 這個 stage 要把結果寫進哪個 key
    result_key: str
    # worker / coder 用來驅動子圖內部路由
    next_step: str
    # coder -> sandbox -> parser 的中繼欄位（留在子圖內，不外流）
    generated_code: str
    sandbox_stdout: str
    sandbox_stderr: str
    error_traceback: str
    execution_status: str
    # parser 依 result_key 寫入其中之一
    weather_result: dict[str, Any]
    travel_result: dict[str, Any]
    booking_result: dict[str, Any]
    budget_result: dict[str, Any]
    traffic_result: dict[str, Any]
    scheduler_result: dict[str, Any]


STAGE_LABELS = {
    "budget": "預算管家",
    "weather": "天氣專員",
    "travel": "景點專員",
    "booking": "訂房專員",
    "traffic": "交通專員",
    "scheduler": "排程專員",
}


def build_stage_subgraph(worker_node: Callable):
    """把 worker -> coder -> e2b_sandbox -> parser 組成一張可執行子圖。"""
    graph = StateGraph(StageState)
    graph.add_node("worker", worker_node)
    graph.add_node("coder", coder_node)
    graph.add_node("e2b_sandbox", sandbox_node)
    graph.add_node("parser", parser_node)

    graph.set_entry_point("worker")
    # worker 成功 -> coder；worker 失敗 (next_step=FINISH) -> 直接結束
    graph.add_conditional_edges(
        "worker",
        lambda s: s.get("next_step", "coder"),
        {"coder": "coder", "final_response": END, "FINISH": END},
    )
    # coder 成功 -> e2b_sandbox；coder 失敗 -> 結束
    graph.add_conditional_edges(
        "coder",
        lambda s: s.get("next_step", "FINISH"),
        {"e2b_sandbox": "e2b_sandbox", "FINISH": END},
    )
    graph.add_edge("e2b_sandbox", "parser")
    graph.add_edge("parser", END)
    return graph.compile()


# --- 父圖用的 context / 摘要工具 -----------------------------------------
def _extract_user_query(state: AgentState) -> str:
    messages = state.get("messages") or []
    if messages:
        return str(messages[0].content)
    return str(state.get("user_query", ""))


def _format_upstream_context(state: AgentState) -> str:
    """把目前已經跑完的上游 agent 資料整理成文字，注入下游 stage。"""
    parts: list[str] = []
    tier = state.get("budget_tier")
    if tier:
        parts.append(f"預算階層：{tier}")
    for label, key in (
        ("預算估算", "budget_result"),
        ("天氣", "weather_result"),
        ("景點", "travel_result"),
        ("訂房", "booking_result"),
        ("交通", "traffic_result"),
    ):
        value = state.get(key)
        if value:
            parts.append(f"{label}：{json.dumps(value, ensure_ascii=False)}")
    return "\n".join(parts)


def _summarize(stage_name: str, result: dict, out: dict) -> AIMessage:
    label = STAGE_LABELS.get(stage_name, stage_name)
    if result:
        preview = json.dumps(result, ensure_ascii=False)
        if len(preview) > 500:
            preview = preview[:500] + "..."
        return AIMessage(content=f"[{label}] 已完成並取得結果：{preview}")
    status = out.get("execution_status", "")
    err = str(out.get("error_traceback", ""))
    reason = f" 原因：{err[:200]}" if err else ""
    return AIMessage(content=f"[{label}] 未取得結構化結果 (status={status})。{reason}")


# --- 預算階層判斷（預算管家的職責）--------------------------------------
_ZH_DIGITS = {
    "零": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _zh_to_int(token: str):
    if token.isdigit():
        return int(token)
    if token in _ZH_DIGITS:
        return _ZH_DIGITS[token]
    # 處理「十X」「X十」「X十Y」等簡單情況
    if "十" in token:
        left, _, right = token.partition("十")
        tens = _ZH_DIGITS.get(left, 1) if left else 1
        ones = _ZH_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def classify_budget_tier(user_query: str) -> str:
    """依使用者輸入的『每人每天預算』粗分為 窮遊 / 適中 / 寬裕。

    這是預算管家的判斷邏輯（規則式，可日後換成 LLM）；無法判斷金額時預設「適中」。
    """
    text = user_query or ""

    amount = None
    m = re.search(r"預算[^\d]{0,8}(\d[\d,]*)", text)
    if not m:
        m = re.search(r"(\d[\d,]*)\s*(?:元|塊|NT\$?|nt\$?|台幣|新台幣|TWD)", text)
    if m:
        amount = int(m.group(1).replace(",", ""))

    days = None
    md = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*天", text)
    if md:
        days = _zh_to_int(md.group(1))

    people = 1
    mp = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*(?:人|位)", text)
    if mp:
        parsed_people = _zh_to_int(mp.group(1))
        if parsed_people:
            people = max(1, parsed_people)

    if amount is None:
        return "適中"

    per_day = amount / (people * (days or 1))
    if per_day < 1500:
        return "窮遊"
    if per_day <= 3500:
        return "適中"
    return "寬裕"


# --- 對外：把一個 stage 包成父圖的 node ---------------------------------
def make_stage_node(worker_node: Callable, result_key: str, stage_name: str) -> Callable:
    subgraph = build_stage_subgraph(worker_node)

    def stage_node(state: AgentState) -> dict:
        user_query = _extract_user_query(state)
        context = _format_upstream_context(state)

        seed_messages: list[BaseMessage] = [HumanMessage(content=user_query)]
        if context:
            seed_messages.append(
                HumanMessage(content=f"【上游 agent 已提供的資料】\n{context}")
            )

        out = subgraph.invoke({
            "messages": seed_messages,
            "result_key": result_key,
            "next_step": "",
        })

        result = out.get(result_key) or {}
        code = str(out.get("generated_code", ""))

        update: dict[str, Any] = {
            "messages": [_summarize(stage_name, result, out)],
            "stage_logs": [{
                "stage": stage_name,
                "result_key": result_key,
                "status": out.get("execution_status", ""),
                "has_result": bool(result),
                "code_chars": len(code),
            }],
        }
        if result:
            update[result_key] = result
        if stage_name == "budget":
            # 預算管家判斷階層，供 supervisor 轉發給後續 agent
            update["budget_tier"] = classify_budget_tier(user_query)
        return update

    return stage_node
