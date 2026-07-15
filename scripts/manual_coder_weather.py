import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _has_api_key(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _configure_openrouter_key() -> bool:
    if _has_api_key("OPENAI_API_KEY"):
        return True

    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        os.environ["OPENAI_API_KEY"] = openrouter_key
        return True

    return False


def _has_e2b_api_key() -> bool:
    api_key = (os.getenv("E2B_API_KEY") or "").strip()
    return bool(api_key and api_key not in {",", "your_e2b_api_key"})


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    if not _configure_openrouter_key():
        print("OPENROUTER_API_KEY or OPENAI_API_KEY is not set. Add one to .env to run this live workflow test.")
        return
    if not _has_e2b_api_key():
        print("E2B_API_KEY is not set. Add it to .env to run this live workflow test.")
        return

    from main import app_graph

    print("🚀 開始測試天氣轉寫 Code 流程...")

    initial_state = {
        "messages": [HumanMessage(content="幫我查一下台北現在的天氣如何？")],
        "next_step": "supervisor",
        "generated_code": "",
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 嘗試執行 (第 {attempt + 1}/{max_retries} 次)...")
            final_state = app_graph.invoke(initial_state)  # type: ignore

            print("\n" + "=" * 50)
            print("🎉 測試結束！來檢查 Coder 有沒有成功寫出 Code：")
            print("=" * 50 + "\n")
            print(final_state.get("generated_code", "沒有寫出code"))
            print("\n\n=== 🕵️ 抓蟲時間 ===")
            print(f"1. 主管最後決定的 next_step 是：{final_state.get('next_step')}")
            break
        except Exception as e:
            if "429" in str(e):
                wait_time = 35
                print(f"⚠️ 遇到 429 塞車了！等待 {wait_time} 秒後自動重試...")
                time.sleep(wait_time)
            else:
                print(f"❌ 發生其他錯誤：{e}")
                break


if __name__ == "__main__":
    main()
