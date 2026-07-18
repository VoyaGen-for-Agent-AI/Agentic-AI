import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.traffic_prompt import TRAFFIC_PROMPT
import time

def build_mock_traffic_result(state: AgentState) -> dict:
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    origin = state.get("departure_station") or state.get("origin") or (
        trip_request.get("departure_station") if isinstance(trip_request, dict) else ""
    ) or "台北車站"
    destination = state.get("destination") or (
        trip_request.get("destination") if isinstance(trip_request, dict) else ""
    ) or "台中"
    segments = [
        {
            "from": origin,
            "to": "台中車站",
            "mode": "台鐵/高鐵",
            "duration_minutes": 90,
            "estimated_cost": 700,
            "note": "實際時間與票價請以訂票系統為準。",
        },
        {
            "from": "台中車站",
            "to": "市區景點",
            "mode": "公車/步行",
            "duration_minutes": 30,
            "estimated_cost": 50,
            "note": "市區景點集中，適合搭配步行。",
        },
    ]
    return {
        "origin": origin,
        "destination": destination,
        "segments": segments,
        "total_transport_time_minutes": sum(segment["duration_minutes"] for segment in segments),
        "total_transport_cost": sum(segment["estimated_cost"] for segment in segments),
        "feasibility": "good",
        "warning": "週末尖峰時段建議提早訂票。",
        "source": "mock_fallback",
        "source_detail": "Traffic API/LLM unavailable or disabled; using mock traffic result.",
    }


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def traffic_node(state: AgentState):
    print("[Traffic Worker] 正在解析使用者交通規劃需求...")

    if (
        not _using_mock_llm()
        and (
            os.getenv("USE_LIVE_TRAFFIC") != "1"
            or not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
        )
    ):
        return {
            "traffic_result": build_mock_traffic_result(state),
            "execution_status": "fallback",
            "error_traceback": "Live traffic disabled or API key not configured; using mock traffic.",
            "current_task": "traffic",
            "next_step": "travel",
        }

    # 1. 初始化 Travel 專員的大腦
    # llm = ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     #model="google/gemma-4-26b-a4b-it:free",
    #     #model="liquid/lfm-2.5-1.2b-thinking:free",
    #     #model="meta-llama/llama-3.3-70b-instruct:free",
    #     model="openai/gpt-oss-20b:free",
    #     api_key=os.getenv("OPENAI_API_KEY") # type: ignore
    # )
    ##############付費#################
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.3-70b-instruct",
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"), # type: ignore
        extra_body={
            "provider": {
                "order": ["DeepInfra"],
                "ignore": ["Nebius Token Factory","AkashML","NovitaAI","Parasail","SambaNova Turbo","Groq","Weight&Biases","Google Vertex", "Together","Cloudflare"],
                "allow_fallbacks": True
            }
        } 
    )
    #################################

    # 2. 抓取使用者的原始問題 (通常是最一開始的那句話)
    user_input = state["messages"][0].content

    # 3. 組裝訊息，讓 LLM 根據 prompt 萃取起點/終點/停靠點並生成規格
    messages = [
        SystemMessage(content=TRAFFIC_PROMPT),
        HumanMessage(content=f"使用者輸入：{user_input}")
    ]

    try:
        response = llm.invoke(messages)

        print("[Traffic Worker] 需求規格產生完成，準備交接給 Coder。")

        # 4. 更新狀態機
        # 把這份規格書加進對話紀錄中，這樣 Coder 的 last_request 才能完美接到這句話
        return {
            "messages": [response],
            "current_task": "traffic",
            "next_step": "coder" # 指派下一步給 Coder Agent 去寫 Code
        }

    except Exception as e:
        print(f"[Traffic Worker] 發生錯誤，改用 mock traffic: {e}")
        return {
            "traffic_result": build_mock_traffic_result(state),
            "execution_status": "fallback",
            "error_traceback": str(e),
            "current_task": "traffic",
            "next_step": "travel",
        }
