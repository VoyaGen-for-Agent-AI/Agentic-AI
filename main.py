import os
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from core.state import AgentState
from agents.supervisor import create_supervisor_node
from agents.workers.mock_workers import weather_node, travel_node, movie_node
from dotenv import load_dotenv

load_dotenv() # 這行會自動把 .env 裡的金鑰載入系統中
if not os.getenv("OPENAI_API_KEY"):
    print("警告：找不到 OPENAI_API_KEY！")
app = FastAPI()

# 1. 初始化 LLM 與大腦邏輯
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",  #把請求導向 OpenRouter
    model="liquid/lfm-2.5-1.2b-thinking:free",
    api_key=os.getenv("OPENAI_API_KEY")# type: ignore
) 
supervisor_chain = create_supervisor_node(llm)

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
workflow.add_node("travel", travel_node)
workflow.add_node("movie", movie_node)

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
        "movie": "movie",
        "FINISH": END
    }
)

# 設定專員執行完後，就結束流程 (回到 END)
workflow.add_edge("weather", END)
workflow.add_edge("travel", END)
workflow.add_edge("movie", END)

# 4. 編譯成可執行的應用程式
app_graph = workflow.compile()

# 建立一個測試用的 API 端點
@app.get("/chat/{query}")
def chat_test(query: str):
    # 將使用者的問題包裝成 HumanMessage 送進去跑
    result = app_graph.invoke({"messages": [HumanMessage(content=query)]})# type: ignore
    # 回傳 Graph 跑完後，陣列裡最後一句 AI 生成的話
    return {"response": result["messages"][-1].content}