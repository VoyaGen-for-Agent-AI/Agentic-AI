"""單獨驗證『景點 (travel)』agent：worker → coder → e2b_sandbox → parser。

新架構下每個 stage 都是獨立子圖，這裡直接跑 travel 子圖，確認 worker 產規格、
coder 寫出 code、sandbox 執行、parser 解析成 travel_result 的整條鏈路是否正常。
"""

from dotenv import load_dotenv
load_dotenv()

import time
from langchain_core.messages import HumanMessage
from agents.stage_graph import build_stage_subgraph
from agents.workers.travel_worker import travel_node


def test_run():
    print("🚀 開始測試『景點 (travel)』agent 轉寫 Code 流程...")

    subgraph = build_stage_subgraph(travel_node)
    init_state = {
        "messages": [HumanMessage(content="幫我排台北兩天一夜行程，我想去故宮博物院，還要吃鼎泰豐。")],
        "result_key": "travel_result",
        "next_step": "",
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 嘗試執行 (第 {attempt + 1}/{max_retries} 次)...")
            final_state = subgraph.invoke(init_state)  # type: ignore

            print("\n" + "=" * 50)
            print("🎉 測試結束！檢查 Coder 有沒有成功寫出 Code：")
            print("=" * 50 + "\n")
            print(final_state.get("generated_code", "沒有寫出 code"))

            print("\n\n=== 🕵️ 抓蟲時間 ===")
            print(f"1. 執行狀態 execution_status：{final_state.get('execution_status')}")
            print(f"2. parser 解析出的 travel_result：{final_state.get('travel_result')}")
            print(f"3. sandbox stderr：{final_state.get('sandbox_stderr')}")
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
    test_run()
