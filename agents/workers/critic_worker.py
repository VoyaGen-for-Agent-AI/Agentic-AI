from typing import Any

from langchain_core.messages import AIMessage

from core.state import AgentState


ERROR_DETAILS = {
    "ModuleNotFoundError": {
        "diagnosis": "The generated code imports a module that is not available in the sandbox.",
        "suggestion": "Use Python standard library modules or install/declare the missing dependency before execution.",
    },
    "SyntaxError": {
        "diagnosis": "The generated code contains invalid Python syntax.",
        "suggestion": "Regenerate or edit the code so it is valid Python before running it again.",
    },
    "NameError": {
        "diagnosis": "The generated code references a variable or function name that is not defined.",
        "suggestion": "Define the missing name before use or correct the typo in the generated code.",
    },
    "TimeoutError": {
        "diagnosis": "The sandbox execution timed out.",
        "suggestion": "Simplify the code, reduce loops or network waits, and run it again with bounded execution.",
    },
    "JSONDecodeError": {
        "diagnosis": "The parser could not decode sandbox stdout as JSON.",
        "suggestion": "Ensure the generated code prints exactly one valid JSON object to stdout.",
    },
    "unknown": {
        "diagnosis": "The error did not match a known execution or parsing failure pattern.",
        "suggestion": "Inspect error_traceback and sandbox_stderr for the underlying cause.",
    },
    "none": {
        "diagnosis": "No sandbox or parser error was found.",
        "suggestion": "No critic action is needed.",
    },
}


def _read_error_text(state: AgentState) -> str:
    error_traceback = state.get("error_traceback") or ""
    sandbox_stderr = state.get("sandbox_stderr") or ""
    return f"{error_traceback}\n{sandbox_stderr}".strip()


def _classify_error(error_text: str) -> str:
    if not error_text:
        return "none"

    if "ModuleNotFoundError" in error_text:
        return "ModuleNotFoundError"
    if "SyntaxError" in error_text:
        return "SyntaxError"
    if "NameError" in error_text:
        return "NameError"
    if "TimeoutError" in error_text or "timeout" in error_text.lower():
        return "TimeoutError"
    if "JSONDecodeError" in error_text:
        return "JSONDecodeError"
    return "unknown"


def _build_critic_result(error_type: str) -> dict[str, str]:
    detail = ERROR_DETAILS[error_type]
    return {
        "error_type": error_type,
        "diagnosis": detail["diagnosis"],
        "suggestion": detail["suggestion"],
    }


def critic_node(state: AgentState) -> dict[str, Any]:
    error_text = _read_error_text(state)
    error_type = _classify_error(error_text)
    critic_result = _build_critic_result(error_type)

    message = (
        f"Critic classified execution issue as {critic_result['error_type']}. "
        f"{critic_result['diagnosis']} Suggestion: {critic_result['suggestion']}"
    )

    return {
        "critic_result": critic_result,
        "messages": [AIMessage(content=message)],
    }
