import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.budget_prompt import BUDGET_PROMPT
import time


def allocate_budget(total_budget: int, days: int, nights: int, preference: str = "") -> dict:
    ratios = {
        "hotel_budget": 0.40,
        "transport_budget": 0.18,
        "food_budget": 0.27,
        "activity_budget": 0.05,
        "buffer_budget": 0.10,
    }

    if "省錢" in preference or "便宜" in preference:
        ratios["hotel_budget"] = 0.35
        ratios["buffer_budget"] = 0.15
    elif "舒適" in preference or "不要太累" in preference:
        ratios["hotel_budget"] = 0.45
        ratios["food_budget"] = 0.24
        ratios["buffer_budget"] = 0.08

    allocation = {
        key: int(total_budget * ratio)
        for key, ratio in ratios.items()
        if key != "buffer_budget"
    }
    allocation["buffer_budget"] = total_budget - sum(allocation.values())
    return allocation


def budget_node(state: AgentState):
    print("💰  [Budget Worker] 正在解析使用者預算估算需求...")
    time.sleep(5)

    # 1. 初始化 Budget 專員的大腦
    llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",  #把請求導向 OpenRouter
    #model="google/gemma-4-26b-a4b-it:free",
    #model="liquid/lfm-2.5-1.2b-thinking:free",
    model="meta-llama/llama-3.3-70b-instruct:free",
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

    # 2. 抓取使用者的原始問題 (通常是最一開始的那句話)
    user_input = state["messages"][0].content

    # 3. 組裝訊息，讓 LLM 根據 prompt 萃取目的地/天數/幣別並生成規格
    messages = [
        SystemMessage(content=BUDGET_PROMPT),
        HumanMessage(content=f"使用者輸入：{user_input}")
    ]

    try:
        response = llm.invoke(messages)

        print(f"📋  [Budget Worker] 需求規格產生完成，準備交接給 Coder。")

        # 4. 更新狀態機
        # 把這份規格書加進對話紀錄中，這樣 Coder 的 last_request 才能完美接到這句話
        return {
            "messages": [response],
            "current_task": "budget",
            "next_step": "coder" # 指派下一步給 Coder Agent 去寫 Code
        }

    except Exception as e:
        print(f"⚠️  [Budget Worker] 發生錯誤: {e}")
        return {"next_step": "FINISH"}
