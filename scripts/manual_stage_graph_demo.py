"""手動驗證：用 `agents/stage_graph.py` + `agents/supervisor.py` 實際跑完整條流程。

這支腳本組出的是**子圖 + supervisor 架構**本身，也就是 2026-07-11（`5b6d352`）到
07-15（`243eddd`）之間 `main.py` 曾經採用的那張圖：

    supervisor ─┬─> budget ──┐
                ├─> weather ─┤
                ├─> travel ──┤   travel 與 booking 屬同一個平行組，
                ├─> booking ─┤   route_next 會一次回傳兩者做 fan-out
                ├─> traffic ─┤
                └─> scheduler┘
                       │
                  final_response

它和 `scripts/manual_parallel_graph_demo.py` 的差別：那一支是另外自建圖、用注入延遲的
mock 節點量 LangGraph 的併發排程；這一支跑的是真正的 `make_stage_node` 與 `route_next`，
worker 也是 `agents/workers/` 底下的真實 agent。

輸出會驗證三件事：

1. 六個 stage 是否都跑完並產出 result（`stage_logs` 與各 `*_result`）。
2. travel / booking 是否落在不同執行緒、時間是否重疊（平行 fan-out 是否真的生效）。
3. 子圖的中繼欄位（`generated_code`、`sandbox_stdout` 等）有沒有外流到父狀態。

**沒有任何金鑰也能跑完**，各 stage 會走三層降級的 mock。

執行方式：

    poetry run python scripts/manual_stage_graph_demo.py

mock 模式下每個 stage 只花數毫秒，快到看不出重疊。想在畫面上看見平行，設定：

    STAGE_DEMO_DELAY_SECONDS=0.5 poetry run python scripts/manual_stage_graph_demo.py

該延遲是**人工注入**的，只用來讓時間軸重疊可見，不代表任何效能數據。
"""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node  # noqa: E402
from agents.stage_graph import make_stage_node  # noqa: E402
from agents.supervisor import route_next, supervisor_node  # noqa: E402
from agents.workers.booking_worker import booking_node  # noqa: E402
from agents.workers.budget_worker import budget_node  # noqa: E402
from agents.workers.schedule_worker import schedule_node  # noqa: E402
from agents.workers.traffic_worker import traffic_node  # noqa: E402
from agents.workers.travel_worker import travel_node  # noqa: E402
from agents.workers.weather_worker import weather_node  # noqa: E402
from core.state import AgentState  # noqa: E402
from prompts.demo_prompt import DEMO_PROMPT  # noqa: E402


# 順序必須對齊 agents/supervisor.py 的 STAGE_ORDER，否則 supervisor 會要求一個
# 父圖裡不存在的節點，導致 route_next 永遠等不到它完成而無限迴圈。
STAGES: tuple[tuple[str, Callable, str], ...] = (
    ("budget", budget_node, "budget_result"),
    ("weather", weather_node, "weather_result"),
    ("travel", travel_node, "travel_result"),
    ("booking", booking_node, "booking_result"),
    ("traffic", traffic_node, "traffic_result"),
    ("scheduler", schedule_node, "scheduler_result"),
)

# 子圖內部才有的中繼欄位；這些一旦出現在父狀態，就代表隔離失效
INTERNAL_KEYS = ("generated_code", "sandbox_stdout", "sandbox_stderr")

_timeline: list[dict[str, Any]] = []
_timeline_lock = threading.Lock()


def _injected_delay() -> float:
    try:
        return max(0.0, float(os.getenv("STAGE_DEMO_DELAY_SECONDS", "0")))
    except ValueError:
        return 0.0


def _instrument(node: Callable, stage_name: str) -> Callable:
    """包一層計時，記錄每個 stage 的起訖時間與執行緒，用來判斷是否真的平行。"""
    delay = _injected_delay()

    def wrapped(state: AgentState) -> dict:
        if delay:
            time.sleep(delay)
        started = time.perf_counter()
        try:
            return node(state)
        finally:
            ended = time.perf_counter()
            with _timeline_lock:
                _timeline.append({
                    "stage": stage_name,
                    "thread": threading.current_thread().name,
                    "start": started,
                    "end": ended,
                })

    return wrapped


def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor_node)
    for stage_name, worker, result_key in STAGES:
        workflow.add_node(
            stage_name,
            _instrument(make_stage_node(worker, result_key, stage_name), stage_name),
        )
    workflow.add_node("final_response", final_response_node)

    workflow.set_entry_point("supervisor")
    # route_next 回傳 list 時 LangGraph 會在同一個 superstep 同時啟動多個分支
    workflow.add_conditional_edges(
        "supervisor",
        route_next,
        {**{name: name for name, _, _ in STAGES}, "FINISH": "final_response"},
    )
    for stage_name, _, _ in STAGES:
        workflow.add_edge(stage_name, "supervisor")
    workflow.add_edge("final_response", END)
    return workflow.compile()


def _overlaps(first: dict, second: dict) -> bool:
    return first["start"] < second["end"] and second["start"] < first["end"]


def _report(result: dict) -> None:
    print("\n" + "=" * 62)
    print("1. 各 stage 執行結果")
    print("=" * 62)
    logs = result.get("stage_logs", [])
    for log in logs:
        mark = "有結果" if log.get("has_result") else "無結果"
        print(
            f"  {log.get('stage', ''):10s} status={log.get('status', '') or '(空)':12s}"
            f" {mark}  產碼 {log.get('code_chars', 0)} 字元"
        )
    print(f"  完成 {len(logs)} / {len(STAGES)} 個 stage")

    print("\n" + "=" * 62)
    print("2. 平行 fan-out 驗證")
    print("=" * 62)
    delay = _injected_delay()
    if delay:
        print(f"  注意：已注入 {delay} 秒人工延遲，僅為了讓重疊可見，非效能數據。")
    if not _timeline:
        print("  沒有記錄到任何 stage。")
        return
    base = min(entry["start"] for entry in _timeline)
    for entry in sorted(_timeline, key=lambda item: item["start"]):
        print(
            f"  {entry['stage']:10s} {entry['start'] - base:7.3f}s -> "
            f"{entry['end'] - base:7.3f}s  thread={entry['thread']}"
        )
    by_stage = {entry["stage"]: entry for entry in _timeline}
    travel, booking = by_stage.get("travel"), by_stage.get("booking")
    if travel and booking:
        same_thread = travel["thread"] == booking["thread"]
        print(f"\n  travel / booking 不同執行緒：{not same_thread}")
        print(f"  travel / booking 時間重疊：{_overlaps(travel, booking)}")
        if not _overlaps(travel, booking) and not delay:
            print("  （mock 模式每個 stage 僅數毫秒，重疊不易觀察；"
                  "設 STAGE_DEMO_DELAY_SECONDS=0.5 可看見。）")

    print("\n" + "=" * 62)
    print("3. 子圖狀態隔離驗證")
    print("=" * 62)
    leaked = [key for key in INTERNAL_KEYS if key in result]
    print(f"  父狀態收到的 result：{sorted(k for k in result if k.endswith('_result'))}")
    print(f"  外流的子圖中繼欄位：{leaked or '無'}")
    if leaked:
        print("  ⚠️ 隔離失效，請檢查 make_stage_node 的回傳內容。")

    answer = result.get("final_answer") or ""
    print("\n" + "=" * 62)
    print("4. 最終回覆（前 300 字）")
    print("=" * 62)
    print(f"  {answer[:300]}..." if answer else "  （沒有產出最終回覆）")


def main() -> int:
    load_dotenv()
    print("=" * 62)
    print("子圖 + supervisor 架構端到端驗證")
    print("=" * 62)
    print(f"  查詢：{DEMO_PROMPT[:60]}...")
    started = time.perf_counter()
    result = build_graph().invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})
    print(f"\n  總耗時 {time.perf_counter() - started:.3f} 秒")
    _report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
