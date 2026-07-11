import os
import time

import pytest
from langchain_core.messages import HumanMessage

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="test_coder requires OPENAI_API_KEY and calls the live weather stage subgraph",
)


def test_run():
    """單獨驗證『天氣 (weather)』stage 子圖：worker → coder → e2b_sandbox → parser。"""
    from agents.stage_graph import build_stage_subgraph
    from agents.workers.weather_worker import weather_node

    print("🚀 開始測試天氣轉寫 Code 流程...")

    subgraph = build_stage_subgraph(weather_node)
    initial_state = {
        "messages": [HumanMessage(content="幫我查一下台北現在的天氣如何？")],
        "result_key": "weather_result",
        "next_step": "",
    }

    # 加入自動重試機制，最多試 5 次
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 嘗試執行 (第 {attempt + 1}/{max_retries} 次)...")
            final_state = subgraph.invoke(initial_state)  # type: ignore

            print("\n" + "=" * 50)
            print("🎉 測試結束！來檢查 Coder 有沒有成功寫出 Code：")
            print("=" * 50 + "\n")

            code = final_state.get("generated_code", "沒有寫出 code")
            print(code)

            print("\n\n=== 🕵️ 抓蟲時間 ===")
            print(f"1. 執行狀態 execution_status：{final_state.get('execution_status')}")
            print(f"2. parser 解析出的 weather_result：{final_state.get('weather_result')}")

            # 成功跑完就跳出迴圈
            break

        except Exception as e:
            # 如果捕捉到 429 錯誤字眼
            if "429" in str(e):
                wait_time = 35
                print(f"⚠️ 遇到 429 塞車了！等待 {wait_time} 秒後自動重試...")
                time.sleep(wait_time)
            else:
                # 如果是其他程式碼寫錯的 Bug，就直接印出來並停止
                print(f"❌ 發生其他錯誤：{e}")
                break


if __name__ == "__main__":
    test_run()
