import os
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from core.state import AgentState
from agents.supervisor import supervisor_node, route_next
from agents.stage_graph import make_stage_node
from agents.final_response import final_response_node
from agents.workers.weather_worker import weather_node
from agents.workers.travel_worker import travel_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.schedule_worker import schedule_node
from dotenv import load_dotenv

load_dotenv()  # 這行會自動把 .env 裡的金鑰載入系統中
if not os.getenv("OPENAI_API_KEY"):
    print("警告：找不到 OPENAI_API_KEY！")
app = FastAPI()

# Langfuse Callback Handler（v4 從環境變數讀取 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST）
langfuse_handler = CallbackHandler()

# ---------------------------------------------------------------------------
# 構建 Graph 狀態機
#
# supervisor 是確定性的編排 hub；每個 stage 都是一張獨立子圖
# (worker → coder → e2b_sandbox → parser)，由 make_stage_node 包裝後只把該 stage
# 的 result 冒泡回父圖。因此 travel / booking 可以平行執行而不會互相覆蓋狀態。
#
# 流程：supervisor → budget → supervisor → weather → supervisor
#       → [travel ∥ booking] → supervisor → traffic → supervisor
#       → scheduler → supervisor → final_response → END
# ---------------------------------------------------------------------------
workflow = StateGraph(AgentState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("budget", make_stage_node(budget_node, "budget_result", "budget"))
workflow.add_node("weather", make_stage_node(weather_node, "weather_result", "weather"))
workflow.add_node("travel", make_stage_node(travel_node, "travel_result", "travel"))
workflow.add_node("booking", make_stage_node(booking_node, "booking_result", "booking"))
workflow.add_node("traffic", make_stage_node(traffic_node, "traffic_result", "traffic"))
workflow.add_node("scheduler", make_stage_node(schedule_node, "scheduler_result", "scheduler"))
workflow.add_node("final_response", final_response_node)

# 進入點：supervisor
workflow.set_entry_point("supervisor")

# supervisor 依「已完成的 stage」決定下一步（route_next 回傳 list 代表平行 fan-out）
workflow.add_conditional_edges(
    "supervisor",
    route_next,
    {
        "budget": "budget",
        "weather": "weather",
        "travel": "travel",
        "booking": "booking",
        "traffic": "traffic",
        "scheduler": "scheduler",
        "FINISH": "final_response",
    },
)

# 每個 stage 完成後都回到 supervisor，由 supervisor 決定下一棒
for stage in ("budget", "weather", "travel", "booking", "traffic", "scheduler"):
    workflow.add_edge(stage, "supervisor")

workflow.add_edge("final_response", END)

# 編譯成可執行的應用程式
app_graph = workflow.compile()


# 建立一個測試用的 API 端點
@app.get("/chat/{query}")
def chat_test(query: str):
    # 將 handler 透過 config 傳入 invoke，確保整個 Graph 執行過程都被 Langfuse 記錄
    config = {"callbacks": [langfuse_handler]}

    # 將使用者的問題包裝成 HumanMessage 送進去跑
    result = app_graph.invoke({"messages": [HumanMessage(content=query)]}, config)  # type: ignore

    # 回傳 supervisor 彙整後的最終回覆
    return {"response": result["messages"][-1].content}
