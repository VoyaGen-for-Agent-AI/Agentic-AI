"""單獨測試某個 agent stage 的完整流程，把每一步印到 terminal。

流程：worker -> coder -> e2b_sandbox -> parser

用法：
    poetry run python scripts/diagnose_stage.py                      # 預設跑 travel + traffic
    poetry run python scripts/diagnose_stage.py travel               # 只跑 travel
    poetry run python scripts/diagnose_stage.py traffic "台北到高雄"   # 只跑 traffic，並自訂 query
    poetry run python scripts/diagnose_stage.py budget weather       # 一次跑多個

需要 .env 內有 OPENAI_API_KEY（worker/coder LLM）與 E2B_API_KEY（沙盒執行）。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from langchain_core.messages import HumanMessage
from agents.workers.weather_worker import weather_node
from agents.workers.travel_worker import travel_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.schedule_worker import schedule_node
from agents.workers.coder_worker import coder_node
from agents.workers.sandbox_worker import sandbox_node
from agents.workers.parser_worker import parser_node

# stage 名稱 -> (worker 函式, 該 stage 寫回的 result key)
STAGES = {
    "budget": (budget_node, "budget_result"),
    "weather": (weather_node, "weather_result"),
    "travel": (travel_node, "travel_result"),
    "booking": (booking_node, "booking_result"),
    "traffic": (traffic_node, "traffic_result"),
    "scheduler": (schedule_node, "scheduler_result"),
}

# 每個 stage 沒指定 query 時的預設測試句
DEFAULT_QUERIES = {
    "travel": "幫我規劃從台北到台中的兩天一夜旅遊",
    "traffic": "幫我規劃從台北到台中的交通",
    "budget": "台中兩天一夜，預算一人5000元",
    "weather": "台中天氣如何",
    "booking": "幫我找台中的住宿和機票，7月20日出發22日回",
    "scheduler": "幫我把台中景點排成有時間軸的行程",
}


def make_state(query, current_task):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "route": current_task,
        "current_task": current_task,
        "next_step": current_task,
        "budget_tier": "",
        "weather_result": {}, "movie_result": {}, "travel_result": {},
        "booking_result": {}, "budget_result": {}, "scheduler_result": {},
        "safety_result": {}, "traffic_result": {},
        "stage_logs": [],
        "generated_code": "", "sandbox_stdout": "", "sandbox_stderr": "",
        "error_traceback": "", "critic_result": None,
        "execution_status": "success", "retry_count": 0, "final_answer": "",
    }


def apply_update(state, update):
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]


def run_stage(name, query):
    worker_node, result_key = STAGES[name]
    print("\n" + "=" * 80)
    print(f"  STAGE: {name}   (query: {query})")
    print("=" * 80)
    state = make_state(query, name)

    apply_update(state, worker_node(state))
    print(f"\n--- [1] {name} worker 產出的規格書 (交給 coder) ---")
    print(state["messages"][-1].content)
    if state.get("next_step") != "coder":
        print(f"\n⚠️ worker 沒有交棒給 coder (next_step={state.get('next_step')!r})，流程中止。")
        return

    apply_update(state, coder_node(state))
    print(f"\n--- [2] coder 產出的完整程式碼 ({len(state.get('generated_code',''))} 字元) ---")
    print(state.get("generated_code", "<空>"))
    if not state.get("generated_code"):
        print("\n⚠️ coder 沒有產出程式碼，流程中止。")
        return

    apply_update(state, sandbox_node(state))
    print("\n--- [3] E2B 沙盒執行結果 ---")
    print(f"execution_status : {state.get('execution_status')}")
    print(f"sandbox_stdout   : {state.get('sandbox_stdout')!r}")
    print(f"sandbox_stderr   : {state.get('sandbox_stderr')!r}")
    print(f"error_traceback  : {state.get('error_traceback')!r}")

    apply_update(state, parser_node(state))
    print("\n--- [4] parser 解析後結果 ---")
    print(f"execution_status : {state.get('execution_status')}")
    print(f"{result_key} : {state.get(result_key)}")
    print(f"error_traceback  : {state.get('error_traceback')!r}")


def main(argv):
    # argv 可能是：[stage, stage, ...] 或 [stage, query]
    stages = [a for a in argv if a in STAGES]
    custom_query = next((a for a in argv if a not in STAGES), None)

    if not stages:
        stages = ["travel", "traffic"]  # 預設

    for name in stages:
        query = custom_query or DEFAULT_QUERIES.get(name, "幫我規劃台中旅遊")
        run_stage(name, query)

    print("\n" + "=" * 80)
    print("  診斷完成")
    print("=" * 80)


if __name__ == "__main__":
    main(sys.argv[1:])
