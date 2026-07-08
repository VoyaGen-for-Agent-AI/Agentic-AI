import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node
from agents.workers.coder_worker import coder_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node


def _has_api_key(name: str, placeholders: set[str] | None = None) -> bool:
    value = (os.getenv(name) or "").strip()
    placeholders = placeholders or set()
    return bool(value and value not in placeholders)


def _make_state() -> dict:
    query = "幫我查台北天氣，請產生會輸出 JSON 的 Python code"
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "route": "weather",
        "current_task": "weather",
        "next_step": "weather",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": "",
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


def main() -> None:
    load_dotenv()

    if not _has_api_key("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Add it to .env to run coder_node.")
        return

    if not _has_api_key("E2B_API_KEY", placeholders={",", "your_e2b_api_key"}):
        print("E2B_API_KEY is not set. Add it to .env to run the real E2B pipeline.")
        return

    state = _make_state()

    _apply_update(state, coder_node(state))
    print("generated_code:")
    print(state.get("generated_code", ""))
    print()

    if not state.get("generated_code"):
        print("No generated_code produced. Stopping.")
        return

    _apply_update(state, sandbox_node(state))
    print(f"execution_status: {state.get('execution_status', '')}")
    print(f"sandbox_stdout: {state.get('sandbox_stdout', '')}")
    print(f"sandbox_stderr: {state.get('sandbox_stderr', '')}")
    print(f"error_traceback: {state.get('error_traceback', '')}")
    print()

    if state.get("execution_status") != "success":
        print("Sandbox execution did not succeed. Stopping before parser_node.")
        return

    _apply_update(state, parser_node(state))
    print(f"weather_result: {state.get('weather_result', {})}")
    print(f"movie_result: {state.get('movie_result', {})}")
    print(f"travel_result: {state.get('travel_result', {})}")
    print()

    _apply_update(state, final_response_node(state))
    print(f"final_answer: {state.get('final_answer', '')}")


if __name__ == "__main__":
    main()
