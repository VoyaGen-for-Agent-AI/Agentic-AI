from core import sandbox as sandbox_runner
from core.state import AgentState


def sandbox_node(state: AgentState) -> dict:
    code = state.get("generated_code")
    if not code:
        return {
            "execution_status": "error",
            "error_traceback": "No generated_code found.",
            "sandbox_stdout": "",
            "sandbox_stderr": "",
        }

    result = sandbox_runner.run_python_in_sandbox(code)
    status = result.get("status", "error")
    error = result.get("error") or ""

    if status == "skipped":
        status = "error"

    return {
        "sandbox_stdout": result.get("stdout", "") or "",
        "sandbox_stderr": result.get("stderr", "") or "",
        "error_traceback": error,
        "execution_status": status,
    }
