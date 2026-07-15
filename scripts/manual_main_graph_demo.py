import sys
from pathlib import Path

from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import app_graph


DEMO_PROMPT = "我想在 7/18 到 7/19 從台北車站出發去台中兩天一夜，一人總預算 6000 元，希望行程不要太趕，想安排戶外景點，也請幫我找交通方便的住宿，最後估算整趟旅程的總花費。"


def main() -> int:
    state = app_graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    for key in (
        "trip_request",
        "weather_result",
        "spot_result",
        "booking_result",
        "traffic_result",
        "itinerary_result",
        "travel_result",
        "budget_result",
    ):
        print(f"{key}:")
        print(state.get(key, {}))
        print()

    print("final_answer:")
    print(state.get("final_answer", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
