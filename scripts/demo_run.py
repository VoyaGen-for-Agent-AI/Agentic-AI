"""Demo 入口：用完整化後的 DEMO_PROMPT 跑一次完整 pipeline。

流程：supervisor → budget → weather → [travel ∥ booking] → traffic → scheduler
      → final_response

注意：這會實際呼叫各 worker 的 LLM 與 E2B sandbox、以及外部 API
(OpenWeather / Tavily / 交通部 TDX)，請先在 .env 設定好對應金鑰
（含 E2B_API_KEY 與 TDX_CLIENT_ID / TDX_CLIENT_SECRET）。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.demo_prompt import DEMO_PROMPT  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        print("缺少 OPENAI_API_KEY，請先在 .env 設定後再執行。")
        return 1

    for optional in ("E2B_API_KEY", "TDX_CLIENT_ID", "TDX_CLIENT_SECRET"):
        if not os.getenv(optional):
            print(f"⚠️  提醒：未設定 {optional}，相關 stage 可能無法取得真實結果。")

    try:
        from main import app_graph, langfuse_handler
    except Exception as exc:
        print(f"無法載入 main.py 的 app_graph：{exc}")
        return 1

    print("=" * 60)
    print("Demo Prompt：")
    print(DEMO_PROMPT)
    print("=" * 60)

    result = app_graph.invoke(
        {"messages": [HumanMessage(content=DEMO_PROMPT)]},
        config={"callbacks": [langfuse_handler]},
    )

    print("\n===== 各 stage 執行紀錄 (stage_logs) =====")
    for log in result.get("stage_logs", []):
        print(log)

    print("\n===== 預算階層 =====")
    print(result.get("budget_tier"))

    print("\n===== 最終回覆 (final_answer) =====")
    final_answer = result.get("final_answer")
    if not final_answer and result.get("messages"):
        final_answer = result["messages"][-1].content
    print(final_answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
