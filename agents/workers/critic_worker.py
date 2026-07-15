from typing import Any

from langchain_core.messages import AIMessage

from core.state import AgentState


ERROR_FEEDBACK = {
    "invalid_json": {
        "reason": "The agent output is not valid JSON.",
        "fix_strategy": "Ensure the AI itinerary agent only outputs valid JSON without Markdown or extra text.",
        "should_retry": True,
        "fallback_strategy": "Use mock itinerary_result and continue booking/budget flow.",
    },
    "runtime_error": {
        "reason": "The workflow encountered a runtime error.",
        "fix_strategy": "Inspect error_traceback and validate the failing node inputs before retrying.",
        "should_retry": True,
        "fallback_strategy": "Use the safest available mock result and continue to final_response.",
    },
    "timeout": {
        "reason": "The operation timed out before producing a valid result.",
        "fix_strategy": "Retry with a shorter prompt, simpler computation, or stricter timeout bounds.",
        "should_retry": True,
        "fallback_strategy": "Use cached or mock results for the affected step.",
    },
    "empty_result": {
        "reason": "The agent did not find any valid candidates.",
        "fix_strategy": "Relax constraints or use fallback mock data.",
        "should_retry": False,
        "fallback_strategy": "Use predefined fallback recommendations.",
    },
    "missing_fields": {
        "reason": "Required state fields are missing or malformed.",
        "fix_strategy": "Validate trip_request and downstream result schemas before running the next node.",
        "should_retry": False,
        "fallback_strategy": "Fill missing fields with safe defaults and continue.",
    },
    "api_error": {
        "reason": "An upstream provider or API returned an error.",
        "fix_strategy": "Check credentials, provider status, and model availability before retrying.",
        "should_retry": True,
        "fallback_strategy": "Use mock itinerary_result instead of live AI generation.",
    },
    "over_budget": {
        "reason": "The estimated trip cost exceeds the user budget.",
        "fix_strategy": "Reduce hotel, transportation, or activity costs.",
        "should_retry": False,
        "fallback_strategy": "Return budget adjustment suggestions to the user.",
    },
    "rate_limit": {
        "reason": "The upstream LLM provider is temporarily rate-limited.",
        "fix_strategy": "Retry after the suggested delay or switch to another model.",
        "should_retry": True,
        "fallback_strategy": "Use mock itinerary_result instead of live AI generation.",
    },
    "unknown_error": {
        "reason": "The error did not match a known failure pattern.",
        "fix_strategy": "Inspect error_traceback, sandbox_stderr, and node outputs for the root cause.",
        "should_retry": False,
        "fallback_strategy": "Return a graceful fallback answer with available partial results.",
    },
}


def _combined_error_text(state: AgentState) -> str:
    parts = [
        state.get("error_traceback") or "",
        state.get("sandbox_stderr") or "",
    ]
    return "\n".join(str(part) for part in parts if part).strip()


def _classify_error(state: AgentState) -> str:
    execution_status = state.get("execution_status", "")
    budget_result = state.get("budget_result", {})
    error_text = _combined_error_text(state)
    lower_error = error_text.lower()

    if execution_status == "empty_result":
        return "empty_result"
    if any(pattern in lower_error for pattern in ("json", "jsondecodeerror", "invalid json", "invalid itinerary json")):
        return "invalid_json"
    if "timeout" in lower_error or "timed out" in lower_error:
        return "timeout"
    if "429" in lower_error or "rate limit" in lower_error or "rate-limited" in lower_error:
        return "rate_limit"
    if any(pattern in error_text for pattern in ("API", "401", "403", "502", "provider")):
        return "api_error"
    if execution_status == "over_budget" or (
        isinstance(budget_result, dict) and budget_result.get("status") == "over_budget"
    ):
        return "over_budget"
    if any(pattern in lower_error for pattern in ("missing", "keyerror", "required field")):
        return "missing_fields"
    if execution_status == "error":
        return "runtime_error"
    return "unknown_error"


def _build_feedback(error_type: str) -> dict[str, Any]:
    detail = ERROR_FEEDBACK[error_type]
    return {
        "error_type": error_type,
        "reason": detail["reason"],
        "fix_strategy": detail["fix_strategy"],
        "should_retry": detail["should_retry"],
        "fallback_strategy": detail["fallback_strategy"],
    }


def critic_node(state: AgentState) -> dict[str, Any]:
    error_type = _classify_error(state)
    critic_feedback = _build_feedback(error_type)
    current_task = state.get("current_task", "")

    message = (
        f"Critic feedback: {critic_feedback['error_type']}. "
        f"{critic_feedback['reason']} Fix: {critic_feedback['fix_strategy']}"
    )

    return {
        "critic_feedback": critic_feedback,
        "critic_result": critic_feedback,
        "current_task": current_task,
        "next_step": "final_response",
        "messages": [AIMessage(content=message)],
    }
