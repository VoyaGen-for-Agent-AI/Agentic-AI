"""Supervisor：確定性的編排 hub。

不再用 LLM 猜下一步，而是依「已完成的 stage」決定固定的執行順序：

    budget → weather → [travel, booking 平行] → traffic → scheduler → FINISH

每個 stage 跑完都會回到 supervisor，由 supervisor 決定下一棒；並用 stage_logs
（而不是 result 是否存在）來判斷進度，這樣即使某個 stage 因為外部 API/E2B 失敗
沒有產出 result，流程仍會往前走，不會卡在原地無限迴圈。
"""

from typing import Union
from core.state import AgentState


# 固定的執行順序；travel 與 booking 視為同一階段（平行）
STAGE_ORDER = ["budget", "weather", ("travel", "booking"), "traffic", "scheduler"]


def _completed_stages(state: AgentState) -> set[str]:
    logs = state.get("stage_logs") or []
    return {
        stage
        for log in logs
        if isinstance(log, dict) and isinstance(stage := log.get("stage"), str)
    }


def supervisor_node(state: AgentState) -> dict:
    """純編排節點：本身不改變狀態，只作為回流的匯集點。"""
    return {}


def route_next(state: AgentState) -> Union[str, list[str]]:
    """依已完成的 stage 決定下一步；回傳 list 代表要平行 fan-out。"""
    done = _completed_stages(state)

    for step in STAGE_ORDER:
        if isinstance(step, tuple):
            pending = [s for s in step if s not in done]
            if pending:
                return pending  # travel / booking 平行處理
        elif step not in done:
            return step

    return "FINISH"
