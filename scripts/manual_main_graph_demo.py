import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import app_graph
from core.observability import get_langfuse_callbacks


DEMO_PROMPT = "我想 7/18 到 7/19 從台北車站去台中兩天一夜，預算 6000，想要不要太趕、戶外景點，也需要住宿和預算估算"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def get_user_query(default_query: str) -> str:
    user_input = input("請輸入旅遊需求，直接 Enter 使用預設範例：\n")
    return user_input.strip() or default_query


def main() -> int:
    show_debug = _env_enabled("DEMO_SHOW_DEBUG")
    if show_debug:
        print(f"Weather provider: {os.getenv('WEATHER_PROVIDER', 'llm')}")
        print(f"Traffic provider: {os.getenv('TRAFFIC_PROVIDER', 'llm')}")
        print(f"Spot provider: {os.getenv('SPOT_PROVIDER', 'mock')}")
        if _env_enabled("USE_LIVE_WEATHER"):
            print("Weather live mode enabled")
        if _env_enabled("USE_LIVE_TRAFFIC"):
            print("Traffic live mode enabled")
        if _env_enabled("USE_LIVE_ITINERARY"):
            print("Itinerary live mode enabled")

    user_query = get_user_query(DEMO_PROMPT)
    print(f"user_query: {user_query}")
    callbacks = get_langfuse_callbacks()
    print("Observability enabled" if callbacks else "Observability disabled")
    initial_state = {"messages": [HumanMessage(content=user_query)]}
    state = app_graph.invoke(
        initial_state,
        config={
            "callbacks": callbacks,
            "metadata": {
                "demo": "manual_main_graph_demo",
                "user_query": user_query,
                "weather_provider": os.getenv("WEATHER_PROVIDER"),
                "traffic_provider": os.getenv("TRAFFIC_PROVIDER"),
                "llm_model": os.getenv("LLM_MODEL"),
            },
            "tags": ["demo", "main_graph", "travel_agent"],
        },
    )

    if show_debug:
        for key in ("weather_result", "spot_result", "traffic_result", "itinerary_result"):
            result = state.get(key, {})
            source = result.get("source", "unknown") if isinstance(result, dict) else "unknown"
            print(f"{key} source: {source}")

        for key in (
            "trip_request",
            "weather_result",
            "spot_result",
            "booking_result",
            "traffic_result",
            "itinerary_result",
            "travel_result",
            "budget_result",
            "e2b_validation_result",
        ):
            result = state.get(key, {})
            if isinstance(result, dict) and result.get("source"):
                print(f"[{key}] source: {result['source']}")
            print(f"{key}:")
            print(result)
            print()
        print(f"generated_code exists: {bool(state.get('generated_code'))}")
        print(f"execution_status: {state.get('execution_status', '')}")
        print(f"sandbox_stdout: {state.get('sandbox_stdout', '')}")
        print(f"sandbox_stderr: {state.get('sandbox_stderr', '')}")

    print("final_answer:")
    print(state.get("final_answer", ""))
    if show_debug and state.get("execution_status") == "fallback" and state.get("error_traceback"):
        print("\nerror_traceback:")
        print(state["error_traceback"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
