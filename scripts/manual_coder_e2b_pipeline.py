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


def _configure_openrouter_key() -> bool:
    if _has_api_key("OPENAI_API_KEY"):
        return True

    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        os.environ["OPENAI_API_KEY"] = openrouter_key
        return True

    return False


def _make_state() -> dict:
    query = "請產生一段 Python code，最後只 print 合法 JSON，內容是台北天氣 mock data"
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
        "budget_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
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


def _classify_sandbox_error(state: dict) -> str:
    error_text = " ".join(
        [
            str(state.get("error_traceback", "")),
            str(state.get("sandbox_stderr", "")),
        ]
    ).lower()

    if "auth" in error_text or "unauthorized" in error_text or "forbidden" in error_text:
        return "E2B auth"
    if "network" in error_text or "connect" in error_text or "winerror 10013" in error_text:
        return "network"
    if "syntaxerror" in error_text or "invalid syntax" in error_text:
        return "generated_code syntax error"
    if "modulenotfounderror" in error_text or "no module named" in error_text:
        return "missing package"
    return "unknown"


def main() -> None:
    load_dotenv()

    if not _configure_openrouter_key():
        print("OPENROUTER_API_KEY or OPENAI_API_KEY is not set. Add one to .env to run coder_node.")
        return

    if not _has_api_key("E2B_API_KEY", placeholders={",", "your_e2b_api_key"}):
        print("E2B_API_KEY is not set. Add it to .env to run the real E2B pipeline.")
        return

    state = _make_state()
    summary = {
        "coder_generated_code": "no",
        "e2b_execution": "no",
        "parser_success": "no",
        "final_response_success": "no",
    }

    _apply_update(state, coder_node(state))
    print("generated_code:")
    print(state.get("generated_code", ""))
    if state.get("error_traceback"):
        print(f"coder error: {state['error_traceback']}")
    print()

    if not state.get("generated_code"):
        print("No generated_code produced. Coder Agent failed.")
        print(f"summary: {summary}")
        return
    summary["coder_generated_code"] = "yes"

    _apply_update(state, sandbox_node(state))
    print(f"execution_status: {state.get('execution_status', '')}")
    print(f"sandbox_stdout: {state.get('sandbox_stdout', '')}")
    print(f"sandbox_stderr: {state.get('sandbox_stderr', '')}")
    print(f"error_traceback: {state.get('error_traceback', '')}")
    print()

    if state.get("execution_status") != "success":
        print(f"error_layer: {_classify_sandbox_error(state)}")
        print("Sandbox execution did not succeed. Stopping before parser_node.")
        print(f"summary: {summary}")
        return
    summary["e2b_execution"] = "yes"

    _apply_update(state, parser_node(state))
    print(f"weather_result: {state.get('weather_result', {})}")
    print(f"movie_result: {state.get('movie_result', {})}")
    print(f"travel_result: {state.get('travel_result', {})}")
    if state.get("execution_status") != "success" or state.get("error_traceback"):
        print(f"parser error: {state.get('error_traceback', '')}")
    print()

    if state.get("execution_status") == "success" and state.get("weather_result"):
        summary["parser_success"] = "yes"

    _apply_update(state, final_response_node(state))
    print(f"final_answer: {state.get('final_answer', '')}")
    if state.get("final_answer"):
        summary["final_response_success"] = "yes"

    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
