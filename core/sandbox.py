import importlib
import os
from typing import Any, Literal


SandboxStatus = Literal["success", "error", "timeout", "skipped"]
SandboxResponse = dict[str, str | None]

# coder 產生的程式碼會在「遠端沙盒」執行，讀不到本機 .env，因此需要把它真正
# 用得到的「資料類」API 金鑰明確注入沙盒環境變數。
# 刻意只放資料類金鑰，不注入 OPENAI_API_KEY / E2B_API_KEY / LANGFUSE_* 等敏感金鑰：
# 產生的程式碼不該用到它們，也避免把它們送進遠端執行的任意程式碼中。
SANDBOX_ENV_ALLOWLIST = ("OPENWEATHER_API_KEY", "TAVILY_API_KEY")
_ENV_PLACEHOLDERS = {"", ",", "your_api_key"}


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
    text = _get_attr(result, "text")

    if logs is not None:
        stdout = stdout if stdout is not None else _get_attr(logs, "stdout")
        stderr = stderr if stderr is not None else _get_attr(logs, "stderr")

    if stdout is None and text is not None:
        stdout = text

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
    create = getattr(sandbox_class, "create", None)
    if callable(create):
        try:
            return create(api_key=api_key)
        except TypeError:
            return create()

    try:
        return sandbox_class(api_key=api_key)
    except TypeError:
        return sandbox_class()


def _collect_sandbox_envs() -> dict[str, str]:
    """從本機環境挑出白名單內、且有實際值的金鑰，準備注入沙盒。"""
    envs: dict[str, str] = {}
    for name in SANDBOX_ENV_ALLOWLIST:
        value = (os.getenv(name) or "").strip()
        if value and value not in _ENV_PLACEHOLDERS:
            envs[name] = value
    return envs


def _run_code(sandbox: Any, code: str, envs: dict[str, str]) -> Any:
    """執行程式碼並注入 envs；若該版本 SDK / mock 不支援 envs，退回不帶 envs 呼叫。"""
    if envs:
        try:
            return sandbox.run_code(code, envs=envs)
        except TypeError:
            pass
    return sandbox.run_code(code)


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
        result = _run_code(sandbox, code, _collect_sandbox_envs())

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
