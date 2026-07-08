import json
from json import JSONDecodeError
from typing import Any

from core.state import AgentState


RESULT_KEYS = {
    "weather": "weather_result",
    "movie": "movie_result",
    "travel": "travel_result",
    "booking": "booking_result",
    "budget": "budget_result",
    "scheduler": "scheduler_result",
    "traffic": "traffic_result",
}

NON_TASK_STEPS = {"coder", "e2b_sandbox", "parser", "final_response", "FINISH"}


def _select_result_key(state: AgentState) -> str:
    for task in (state.get("current_task"), state.get("route"), state.get("next_step")):
        if task in NON_TASK_STEPS:
            continue
        if task in RESULT_KEYS:
            return RESULT_KEYS[task]
    return ""


def parser_node(state: AgentState) -> dict[str, Any]:
    if state.get("execution_status") != "success":
        return {
            "execution_status": "error",
            "error_traceback": state.get("error_traceback")
            or "Sandbox execution did not succeed.",
        }

    stdout = state.get("sandbox_stdout", "")
    if not stdout:
        return {
            "execution_status": "error",
            "error_traceback": "No sandbox_stdout found.",
        }

    try:
        parsed_stdout = json.loads(stdout)
    except JSONDecodeError as exc:
        return {
            "execution_status": "error",
            "error_traceback": f"JSONDecodeError: invalid JSON in sandbox_stdout: {exc}",
        }

    result_key = _select_result_key(state)
    if not result_key:
        return {
            "execution_status": "error",
            "error_traceback": "Unable to determine result target.",
        }

    return {
        result_key: parsed_stdout,
        "execution_status": "success",
        "error_traceback": "",
    }
