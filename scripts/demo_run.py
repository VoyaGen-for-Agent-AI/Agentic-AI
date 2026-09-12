"""Demo 入口：用完整化後的 DEMO_PROMPT 跑一次 main.py 的完整 pipeline。

實際流程（對齊 main.py 的 app_graph）：

    trip_parser -> weather -> spot -> booking -> traffic -> travel
                -> e2b_validation -> budget -> final_response

各 stage 都有「真實 API -> LLM 生成 -> 內建 mock」三層降級，因此**沒有金鑰也跑得完**，
只是結果會標示成 mock。若要看到真實資料，請在 .env 依需求設定：

- OPENROUTER_API_KEY 或 OPENAI_API_KEY：LLM 生成（coder / weather / spot / traffic / itinerary）
- OPENWEATHER_API_KEY：搭配 USE_LIVE_WEATHER=1 與 WEATHER_PROVIDER=openweather
- TAVILY_API_KEY：搭配 USE_LIVE_TRAFFIC=1 / USE_LIVE_SPOT=1 等旗標
- E2B_API_KEY：e2b_validation stage 的沙盒檢查，未設定時該 stage 會標成 skipped
- LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY：Langfuse trace，未設定時自動略過

執行方式：poetry run python scripts/demo_run.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prompts.demo_prompt import DEMO_PROMPT  # noqa: E402


# 缺少這些金鑰不會讓 pipeline 中斷，只會讓對應 stage 退回 mock / skipped，
# 因此一律以提醒處理，不直接結束程式。
OPTIONAL_KEYS = (
    ("OPENROUTER_API_KEY / OPENAI_API_KEY", "LLM 生成將全面退回 mock"),
    ("OPENWEATHER_API_KEY", "天氣 stage 無法取得真實預報"),
    ("TAVILY_API_KEY", "景點 / 交通 stage 無法取得搜尋佐證"),
    ("E2B_API_KEY", "e2b_validation stage 會標記為 skipped"),
)


def _missing(key_label: str) -> bool:
    """key_label 允許用 ' / ' 列出多個等效金鑰，任一個有值就算有設定。"""
    return not any(os.getenv(name.strip()) for name in key_label.split("/"))


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    for key_label, consequence in OPTIONAL_KEYS:
        if _missing(key_label):
            print(f"提醒：未設定 {key_label}，{consequence}。")

    try:
        from core.observability import get_langfuse_callbacks
        from main import app_graph
    except Exception as exc:
        print(f"無法載入 main.py 的 app_graph：{exc}")
        return 1

    print("=" * 60)
    print("Demo Prompt：")
    print(DEMO_PROMPT)
    print("=" * 60)

    result = app_graph.invoke(
        {"messages": [HumanMessage(content=DEMO_PROMPT)]},
        config={"callbacks": get_langfuse_callbacks()},
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
