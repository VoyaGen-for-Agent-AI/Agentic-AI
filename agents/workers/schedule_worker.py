import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.schedule_prompt import SCHEDULE_PROMPT
import time

def schedule_node(state: AgentState):
    print("🗓️  [Schedule Worker] 正在彙整景點與交通資訊，規劃時間軸...")
    time.sleep(5)

    # 1. 初始化 Schedule 專員的大腦
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

    # 2. 把對話紀錄中，Travel / Traffic 專員已經產出的規格書內容彙整成字串，
    #    讓 LLM 能從中找出真實的景點與交通資料（不可捏造）
    user_input = state["messages"][0].content
    history_context = "\n".join(
        f"[{msg.type}] {msg.content}" for msg in state["messages"]
    )

    # 3. 組裝訊息交給 LLM
    messages = [
        SystemMessage(content=SCHEDULE_PROMPT),
        HumanMessage(
            content=(
                f"使用者原始需求：{user_input}\n\n"
                f"以下是先前的對話紀錄，請從中找出 Travel 與 Traffic 專員產出的真實景點與交通資料：\n"
                f"{history_context}"
            )
        )
    ]

    try:
        response = llm.invoke(messages)

        print(f"📋  [Schedule Worker] 需求規格產生完成，準備交接給 Coder。")

        # 4. 更新狀態機
        # 把這份規格書加進對話紀錄中，這樣 Coder 的 last_request 才能完美接到這句話
        return {
            "messages": [response],
            "current_task": "scheduler",
            "next_step": "coder" # 指派下一步給 Coder Agent 去寫 Code
        }

    except Exception as e:
        print(f"⚠️  [Schedule Worker] 發生錯誤: {e}")
        return {"next_step": "FINISH"}
