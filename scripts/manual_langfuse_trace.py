import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def missing_env_vars() -> list[str]:
    required = [
        "OPENAI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ]
    missing = [name for name in required if not os.getenv(name)]

    if not (os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")):
        missing.append("LANGFUSE_HOST or LANGFUSE_BASE_URL")

    return missing


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    missing = missing_env_vars()
    if missing:
        print("缺少必要環境變數，請先在 .env 設定後再執行：")
        for name in missing:
            print(f"- {name}")
        return 1

    try:
        from core.observability import get_langfuse_callbacks
        from main import app_graph
    except Exception as exc:
        print("無法載入 main.py 的 app_graph 或 Langfuse callbacks。")
        print(f"錯誤：{exc}")
        return 1

    query = "幫我查天氣"
    print(f"測試 query：{query}")

    try:
        result = app_graph.invoke(
            {"messages": [HumanMessage(content=query)]},
            config={"callbacks": get_langfuse_callbacks()},
        )
    except Exception as exc:
        print("workflow 執行失敗，請檢查 OPENAI_API_KEY、模型設定或網路連線。")
        print(f"錯誤：{exc}")
        return 1

    final_answer = result.get("final_answer")
    if not final_answer and result.get("messages"):
        final_answer = result["messages"][-1].content

    print(f"final_answer：{final_answer}")
    print("請到 Langfuse dashboard 檢查是否有完整 trace：User → Supervisor → Mock Worker → Final Response")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
