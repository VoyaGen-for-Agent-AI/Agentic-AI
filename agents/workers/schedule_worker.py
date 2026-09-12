import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.schedule_prompt import SCHEDULE_PROMPT
import time


# 與 coder_worker 相同的節流開關，見該檔說明；預設關閉，由 LLM_THROTTLE_SECONDS 控制。
def _throttle_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("LLM_THROTTLE_SECONDS", "0")))
    except ValueError:
        return 0.0


def schedule_node(state: AgentState):
    print("[Schedule Worker] 正在彙整景點與交通資訊，規劃時間軸...")
    throttle = _throttle_seconds()
    if throttle:
        time.sleep(throttle)

    # 1. 初始化 Schedule 專員的大腦
#     llm = ChatOpenAI(
#     base_url="https://openrouter.ai/api/v1",  #把請求導向 OpenRouter
#     #model="google/gemma-4-26b-a4b-it:free",
#     #model="liquid/lfm-2.5-1.2b-thinking:free",
#     model="meta-llama/llama-3.3-70b-instruct:free",
#     #model="openai/gpt-oss-20b:free",
#     api_key=os.getenv("OPENAI_API_KEY")# type: ignore
# )
##############付費#################
    # LLM 的建立移到下方 try 內，理由見該處註解。
################################# 

    # 2. 把對話紀錄中，Travel / Traffic 專員已經產出的規格書內容彙整成字串，
    #    讓 LLM 能從中找出真實的景點與交通資料（不可捏造）
    messages = state.get("messages") or []
    if not messages:
        print("[Schedule Worker] 沒有可用的對話紀錄，無法產生規格。")
        return {"next_step": "FINISH"}

    user_input = messages[0].content
    history_context = "\n".join(
        f"[{msg.type}] {msg.content}" for msg in messages
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
        # ChatOpenAI 的建構本身就會驗證憑證，缺金鑰時直接拋 OpenAIError。
        # 放在 try 之外會讓整張圖中斷，而不是讓這個 stage 降級，因此改在這裡建立。
        llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            model="meta-llama/llama-3.1-8b-instruct",
            api_key=os.getenv("OPENAI_API_KEY"),  # type: ignore
            extra_body={
                "provider": {
                    "order": ["DeepInfra", "NovitaAI"],
                    "ignore": ["Cloudflare", "Groq"],
                    "allow_fallbacks": True,
                }
            },
        )
        response = llm.invoke(messages)

        print("[Schedule Worker] 需求規格產生完成，準備交接給 Coder。")

        # 4. 更新狀態機
        # 把這份規格書加進對話紀錄中，這樣 Coder 的 last_request 才能完美接到這句話
        return {
            "messages": [response],
            "current_task": "scheduler",
            "next_step": "coder" # 指派下一步給 Coder Agent 去寫 Code
        }

    except Exception as e:
        print(f"[Schedule Worker] 發生錯誤: {e}")
        return {"next_step": "FINISH"}
