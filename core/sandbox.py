import importlib
import os
from typing import Any, Literal


SandboxStatus = Literal["success", "error", "timeout", "skipped"]
SandboxResponse = dict[str, str | None]


def _sandbox_response(
    status: SandboxStatus,
    stdout: str = "",
    stderr: str = "",
    error: str | None = None,
) -> SandboxResponse:
    return {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
    }


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_to_text(item) for item in value)
    return str(value)


def _get_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _extract_logs(result: Any) -> tuple[str, str]:
    logs = _get_attr(result, "logs")
    stdout = _get_attr(result, "stdout")
    stderr = _get_attr(result, "stderr")

    if logs is not None:
        stdout = stdout if stdout is not None else _get_attr(logs, "stdout")
        stderr = stderr if stderr is not None else _get_attr(logs, "stderr")

    return _to_text(stdout), _to_text(stderr)


def _extract_error(result: Any) -> str | None:
    error = _get_attr(result, "error")
    if error is None:
        return None

    traceback = _get_attr(error, "traceback")
    if traceback:
        return _to_text(traceback)

    error_text = _to_text(error)
    return error_text or None


def _create_sandbox(sandbox_class: Any, api_key: str) -> Any:
    try:
        return sandbox_class(api_key=api_key)
    except TypeError:
        return sandbox_class()


def _close_sandbox(sandbox: Any) -> None:
    for method_name in ("close", "kill"):
        method = getattr(sandbox, method_name, None)
        if callable(method):
            method()
            return


def run_python_in_sandbox(code: str) -> SandboxResponse:
    if not code:
        return _sandbox_response(
            status="error",
            error="No code provided.",
        )

    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        return _sandbox_response(
            status="skipped",
            error="E2B_API_KEY is not set.",
        )

    try:
        e2b_module = importlib.import_module("e2b_code_interpreter")
    except Exception as exc:
        return _sandbox_response(
            status="error",
            error=f"Failed to import e2b_code_interpreter: {exc}",
        )

    sandbox = None
    try:
        sandbox_class = getattr(e2b_module, "Sandbox")
        sandbox = _create_sandbox(sandbox_class, api_key)
        result = sandbox.run_code(code)

        stdout, stderr = _extract_logs(result)
        error = _extract_error(result)
        if error:
            return _sandbox_response(
                status="error",
                stdout=stdout,
                stderr=stderr,
                error=error,
            )

        return _sandbox_response(
            status="success",
            stdout=stdout,
            stderr=stderr,
        )
    except TimeoutError as exc:
        return _sandbox_response(
            status="timeout",
            error=str(exc) or "Sandbox execution timed out.",
        )
    except Exception as exc:
        return _sandbox_response(
            status="error",
            error=str(exc),
        )
    finally:
        if sandbox is not None:
            try:
                _close_sandbox(sandbox)
            except Exception:
                pass
