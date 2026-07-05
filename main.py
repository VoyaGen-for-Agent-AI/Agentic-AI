import os
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from core.state import AgentState
from agents.supervisor import create_supervisor_node
from agents.final_response import final_response_node
from agents.workers.weather_worker import weather_node
from agents.workers.coder_worker import coder_node
from agents.workers.mock_workers import (
    travel_node,
    booking_node,
    financial_node,
    scheduler_node,
    safety_node,
)
from dotenv import load_dotenv

load_dotenv() # 這行會自動把 .env 裡的金鑰載入系統中
if not os.getenv("OPENAI_API_KEY"):
    print("警告：找不到 OPENAI_API_KEY！")
app = FastAPI()

# 1. 初始化 LLM 與大腦邏輯
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",  #把請求導向 OpenRouter
    #model="google/gemma-4-26b-a4b-it:free",
    model="liquid/lfm-2.5-1.2b-thinking:free",
    #model="meta-llama/llama-3.3-70b-instruct:free",
    #model="openai/gpt-oss-20b:free",
    api_key=os.getenv("OPENAI_API_KEY")# type: ignore
)
##############付費#################
    # llm = ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     model="meta-llama/llama-3.1-8b-instruct",
    #     api_key=os.getenv("OPENAI_API_KEY"), # type: ignore
    #     extra_body={
    #         "provider": {
    #             "order": ["DeepInfra","NovitaAI"],
    #             "ignore": ["Cloudflare","Groq"],
    #             "allow_fallbacks": True
    #         }
    #     } 
    # )
################################# 
supervisor_chain = create_supervisor_node(llm)

# 1. 初始化 Langfuse Callback Handler（v4 從環境變數讀取 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST）
langfuse_handler = CallbackHandler()

# 定義一個外層函式來處理狀態流轉
def supervisor_node(state: AgentState):
    # 取出對話紀錄中的最後一句話（也就是使用者剛輸入的話）
    user_input = state["messages"][-1].content
    # 呼叫大腦進行判斷
    result = supervisor_chain.invoke({"input": user_input})
    # 把判斷結果寫回 State 的 next_step 欄位
    return {"next_step": result.next_step}# type: ignore

# 2. 構建 Graph 狀態機
workflow = StateGraph(AgentState)

# 加入所有節點
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("weather", weather_node)
workflow.add_node("coder", coder_node)
workflow.add_node("travel", travel_node)
workflow.add_node("booking", booking_node)
workflow.add_node("financial", financial_node)
workflow.add_node("scheduler", scheduler_node)
workflow.add_node("safety", safety_node)
workflow.add_node("final_response", final_response_node)

# 設定程式進入點
workflow.set_entry_point("supervisor")

# 3. 設定條件邊緣 (Conditional Edges)
workflow.add_conditional_edges(
    "supervisor",
    # 判斷依據：看 state 裡面的 next_step 裝了什麼字串
    lambda x: x["next_step"],
    {
        "weather": "weather",
        "travel": "travel",
        "booking": "booking",
        "financial": "financial",
        "scheduler": "scheduler",
        "safety": "safety",
        "FINISH": END
    }
)
#動態路由：天氣專員產出規格後，判斷下一步 (交給 coder)
workflow.add_conditional_edges(
    "weather",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "FINISH": END
    }
)
#動態路由：工程師寫完 Code 後，判斷下一步 (先導向 END 測試)
workflow.add_conditional_edges(
    "coder",
    lambda x: x.get("next_step", "FINISH"),
    {
        "e2b_sandbox": END, # 因為 E2B 還沒接，先讓他結束，測試能不能印出程式碼
        "FINISH": END
    }
)

# 設定專員執行完後，交給 final_response 整理最終回覆
workflow.add_edge("travel", "final_response")
workflow.add_edge("booking", "final_response")
workflow.add_edge("financial", "final_response")
workflow.add_edge("scheduler", "final_response")
workflow.add_edge("safety", "final_response")
workflow.add_edge("final_response", END)

# 4. 編譯成可執行的應用程式
app_graph = workflow.compile()

# 建立一個測試用的 API 端點
@app.get("/chat/{query}")
def chat_test(query: str):
    # 將 handler 透過 config 傳入 invoke
    # 這會確保整個 Graph 的執行過程都被 Langfuse 記錄下來
    config = {"callbacks": [langfuse_handler]}
    
    # 將使用者的問題包裝成 HumanMessage 送進去跑
    result = app_graph.invoke({"messages": [HumanMessage(content=query)]}, config)# type: ignore
    ################################################
    #測試階段：把產生的程式碼印出來看看！
    generated_code = result.get("generated_code", "")
    if generated_code:
        print("\n\n===== Coder 產出的程式碼 =====")
        print(generated_code)
        print("==============================\n\n")
   ################################################
   
    # 回傳 Graph 跑完後，陣列裡最後一句 AI 生成的話
    return {"response": result["messages"][-1].content}
