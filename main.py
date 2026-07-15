import json
import os
import re
from fastapi import FastAPI
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from core.observability import get_langfuse_callbacks
from core.state import AgentState
from agents.supervisor import create_supervisor_node
from agents.final_response import final_response_node
from agents.workers.weather_worker import weather_node
from agents.workers.travel_worker import travel_node
from agents.workers.coder_worker import coder_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.budget_worker import budget_node
from agents.workers.schedule_worker import schedule_node
from agents.workers.booking_worker import booking_node
from agents.workers.sandbox_worker import sandbox_node
from agents.workers.parser_worker import parser_node
from agents.workers.mock_workers import (
    #weather_node,
    #travel_node,
    #booking_node,
    #financial_node,
    #scheduler_node,
    safety_node,
)
from dotenv import load_dotenv

load_dotenv() # 這行會自動把 .env 裡的金鑰載入系統中
if not os.getenv("OPENAI_API_KEY"):
    print("警告：找不到 OPENAI_API_KEY！")
app = FastAPI()

# 1. 初始化 LLM 與大腦邏輯
llm = ChatOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
    model=os.getenv("LLM_MODEL", "openrouter/free"),
    api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore
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

VALID_ROUTES = {
    "weather",
    "travel",
    "booking",
    "budget",
    "scheduler",
    "traffic",
    "safety",
    "final_response",
    "FINISH",
}

ROUTE_ALIASES = {
    "itinerary": "travel",
    "trip": "travel",
    "trip_planning": "travel",
    "hotel": "booking",
    "accommodation": "booking",
    "lodging": "booking",
    "finance": "budget",
    "cost": "budget",
    "expense": "budget",
}


def normalize_route(raw_output) -> str:
    if hasattr(raw_output, "content"):
        return normalize_route(raw_output.content)

    if isinstance(raw_output, dict):
        raw_route = raw_output.get("next") or raw_output.get("route") or raw_output.get("next_step")
        return normalize_route(raw_route)

    for attr in ("next", "route", "next_step"):
        if hasattr(raw_output, attr):
            return normalize_route(getattr(raw_output, attr))

    if raw_output is None:
        return "travel"

    raw_text = str(raw_output).strip()
    if not raw_text:
        return "travel"

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        return normalize_route(parsed)

    input_value_match = re.search(r"input_value=['\"]([^'\"]+)['\"]", raw_text)
    if input_value_match:
        return normalize_route(input_value_match.group(1))

    normalized_text = raw_text.strip().strip('"').strip("'")
    if normalized_text in VALID_ROUTES:
        return normalized_text

    alias_key = normalized_text.lower().replace("-", "_").replace(" ", "_")
    return ROUTE_ALIASES.get(alias_key, "travel")


# 定義一個外層函式來處理狀態流轉
def supervisor_node(state: AgentState):
    # 取出對話紀錄中的最後一句話（也就是使用者剛輸入的話）
    user_input = state["messages"][-1].content
    try:
        # 呼叫大腦進行判斷
        result = supervisor_chain.invoke({"input": user_input})
        normalized_route = normalize_route(result)
        return {
            "route": normalized_route,
            "next_step": normalized_route,
            "current_task": "supervisor",
        }
    except Exception as error:
        normalized_route = normalize_route(error)
        return {
            "route": normalized_route,
            "next_step": normalized_route,
            "current_task": "supervisor",
            "execution_status": "fallback",
            "error_traceback": str(error),
        }

# 2. 構建 Graph 狀態機
workflow = StateGraph(AgentState)

# 加入所有節點
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("weather", weather_node)
workflow.add_node("coder", coder_node)
workflow.add_node("e2b_sandbox", sandbox_node)
workflow.add_node("parser", parser_node)
workflow.add_node("travel", travel_node)
workflow.add_node("booking", booking_node)
workflow.add_node("budget", budget_node)
workflow.add_node("scheduler", schedule_node)
workflow.add_node("safety", safety_node)
workflow.add_node("traffic", traffic_node)
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
        "budget": "budget",
        "scheduler": "scheduler",
        "safety": "safety",
        "traffic": "traffic",
        "final_response": "final_response",
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
workflow.add_conditional_edges(
    "travel",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "final_response": "final_response",
        "FINISH": END
    }
)
workflow.add_conditional_edges(
    "traffic",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "FINISH": END
    }
)
workflow.add_conditional_edges(
    "budget",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "final_response": "final_response",
        "FINISH": END
    }
)
workflow.add_conditional_edges(
    "scheduler",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "FINISH": END
    }
)
workflow.add_conditional_edges(
    "booking",
    lambda x: x.get("next_step", "FINISH"),
    {
        "coder": "coder",
        "final_response": "final_response",
        "FINISH": END
    }
)


#動態路由：工程師寫完 Code 後，判斷下一步 (交給 e2b_sandbox 執行)
workflow.add_conditional_edges(
    "coder",
    lambda x: x.get("next_step", "FINISH"),
    {
        "e2b_sandbox": "e2b_sandbox",
        "FINISH": END
    }
)

# 設定專員執行完後，交給 final_response 整理最終回覆
#workflow.add_edge("weather", "final_response")
#workflow.add_edge("travel", "final_response")
#workflow.add_edge("booking", "final_response")
#workflow.add_edge("budget", "final_response")
#workflow.add_edge("scheduler", "final_response")
workflow.add_edge("safety", "final_response")
workflow.add_edge("e2b_sandbox", "parser")
workflow.add_edge("parser", "final_response")
workflow.add_edge("final_response", END)

# 4. 編譯成可執行的應用程式
app_graph = workflow.compile()

# 建立一個測試用的 API 端點
@app.get("/chat/{query}")
def chat_test(query: str):
    # 將 handler 透過 config 傳入 invoke
    # 這會確保整個 Graph 的執行過程都被 Langfuse 記錄下來
    config = {"callbacks": get_langfuse_callbacks()}
    
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
