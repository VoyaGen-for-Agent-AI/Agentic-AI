import sys
from pathlib import Path

from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node
from agents.workers.critic_worker import critic_node


def apply_update(state: dict, update: dict) -> None:
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]


def make_invalid_json_state() -> dict:
    return {
        "messages": [HumanMessage(content="請示範 Critic Agent 的錯誤診斷")],
        "user_query": "請示範 Critic Agent 的錯誤診斷",
        "route": "travel",
        "current_task": "travel",
        "next_step": "critic",
        "trip_request": {},
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "itinerary_result": {},
        "booking_result": {},
        "budget_result": {},
        "budget_allocation": {},
        "transport_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": "這不是 JSON",
        "sandbox_stderr": "",
        "error_traceback": "Invalid itinerary JSON: JSONDecodeError",
        "critic_result": None,
        "critic_feedback": None,
        "execution_status": "error",
        "retry_count": 0,
        "final_answer": "",
    }


def main() -> int:
    state = make_invalid_json_state()

    apply_update(state, critic_node(state))  # type: ignore[arg-type]
    apply_update(state, final_response_node(state))  # type: ignore[arg-type]

    print("critic_feedback:")
    print(state.get("critic_feedback", {}))
    print("\nfinal_answer:")
    print(state.get("final_answer", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
