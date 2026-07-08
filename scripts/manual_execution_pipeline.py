import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node


GENERATED_CODE = (
    'print(\'{"location":"Taipei","condition":"rainy",'
    '"temperature":28,"rain_probability":80}\')'
)


def _has_e2b_api_key() -> bool:
    api_key = (os.getenv("E2B_API_KEY") or "").strip()
    return bool(api_key and api_key not in {",", "your_e2b_api_key"})


def _make_state() -> dict:
    return {
        "messages": [HumanMessage(content="手動測試 sandbox execution pipeline")],
        "user_query": "手動測試 sandbox execution pipeline",
        "route": "weather",
        "current_task": "",
        "next_step": "weather",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": GENERATED_CODE,
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def _apply_update(state: dict, update: dict) -> None:
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]


def _print_state(state: dict) -> None:
    print("generated_code:")
    print(state["generated_code"])
    print()
    print(f"sandbox_stdout: {state.get('sandbox_stdout', '')}")
    print(f"weather_result: {state.get('weather_result', {})}")
    print(f"final_answer: {state.get('final_answer', '')}")

    if state.get("error_traceback"):
        print(f"error_traceback: {state['error_traceback']}")


def main() -> None:
    load_dotenv()

    if not _has_e2b_api_key():
        print("E2B_API_KEY is not set. Add it to .env to run the real execution pipeline test.")
        return

    state = _make_state()

    _apply_update(state, sandbox_node(state))
    _apply_update(state, parser_node(state))
    _apply_update(state, final_response_node(state))

    _print_state(state)


if __name__ == "__main__":
    main()
