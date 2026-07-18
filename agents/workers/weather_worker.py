import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.weather_prompt import WEATHER_SYSTEM_PROMPT
import time

def build_mock_weather_result(state: AgentState) -> dict:
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    destination = state.get("destination") or (
        trip_request.get("destination") if isinstance(trip_request, dict) else ""
    ) or "台中"
    return {
        "destination": destination,
        "location": destination,
        "condition": "多雲時晴",
        "rain_probability": 30,
        "temperature": "26-32°C",
        "outdoor_risk": "low",
        "recommendation": "適合安排戶外景點，但午後仍建議保留室內備案。",
        "source": "mock_fallback",
        "source_detail": "Weather API/LLM unavailable or disabled; using mock weather result.",
    }


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def weather_node(state: AgentState):
    print("[Weather Worker] 正在解析使用者天氣需求...")

    if (
        not _using_mock_llm()
        and (
            os.getenv("USE_LIVE_WEATHER") != "1"
            or not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
        )
    ):
        return {
            "weather_result": build_mock_weather_result(state),
            "execution_status": "fallback",
            "error_traceback": "Live weather disabled or API key not configured; using mock weather.",
            "current_task": "weather",
            "next_step": "spot",
        }

    # 1. 初始化 Weather 專員的大腦
    # llm = ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     model="google/gemma-4-26b-a4b-it:free", 
    #     #model="liquid/lfm-2.5-1.2b-thinking:free",
    #     #model="meta-llama/llama-3.3-70b-instruct:free",
    #     #model="openai/gpt-oss-20b:free",
    #     api_key=os.getenv("OPENAI_API_KEY") # type: ignore
    # )
    ##############付費#################
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.1-8b-instruct",
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"), # type: ignore
        extra_body={
            "provider": {
                "order": ["DeepInfra","NovitaAI"],
                "ignore": ["Cloudflare","Groq"],
                "allow_fallbacks": True
            }
        } 
    )
    #################################  

    # 2. 抓取使用者的原始問題 (通常是最一開始的那句話)
    user_input = state["messages"][0].content

    # 3. 組裝訊息，讓 LLM 根據 prompt 萃取城市並生成規格
    messages = [
        SystemMessage(content=WEATHER_SYSTEM_PROMPT),
        HumanMessage(content=f"使用者輸入：{user_input}")
    ]

    try:
        response = llm.invoke(messages)
        
        print("[Weather Worker] 需求規格產生完成，準備交接給 Coder。")
        
        # 4. 更新狀態機
        # 把這份規格書加進對話紀錄中，這樣 Coder 的 last_request 才能完美接到這句話
        return {
            "messages": [response],
            "current_task": "weather",
            "next_step": "coder" # 指派下一步給 Coder Agent 去寫 Code
        }

    except Exception as e:
        print(f"[Weather Worker] 發生錯誤，改用 mock weather: {e}")
        return {
            "weather_result": build_mock_weather_result(state),
            "execution_status": "fallback",
            "error_traceback": str(e),
            "current_task": "weather",
            "next_step": "spot",
        }
