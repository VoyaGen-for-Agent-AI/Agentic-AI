from main import app_graph
from core.state import AgentState
from langchain_core.messages import HumanMessage
import time

def test_run():
    print("🚀 開始測試旅遊轉寫 Code 流程...")
    
    initial_state = {
        "messages": [HumanMessage(content="幫我排台北兩天一夜行程，我想去故宮博物院，還要吃鼎泰豐。")],
        "next_step": "supervisor",
        "generated_code": ""
    }
    
    # 加入自動重試機制，最多試 5 次
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 嘗試執行 (第 {attempt + 1}/{max_retries} 次)...")
            final_state = app_graph.invoke(initial_state) # type: ignore
            
            print("\n" + "="*50)
            print("🎉 測試結束！來檢查 Coder 有沒有成功寫出 Code：")
            print("="*50 + "\n")
            
            code = final_state.get("generated_code", "沒有寫出code")
            print(code)
            
            print("\n\n=== 🕵️ 抓蟲時間 ===")
            print(f"1. 主管最後決定的 next_step 是：{final_state.get('next_step')}")
            
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