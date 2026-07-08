import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.sandbox as sandbox_module
from core.sandbox import run_python_in_sandbox


def assert_sandbox_response(result):
    assert set(result.keys()) == {"status", "stdout", "stderr", "error"}
    assert isinstance(result["status"], str)
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)


def test_empty_code_returns_error():
    result = run_python_in_sandbox("")

    assert_sandbox_response(result)
    assert result["status"] == "error"
    assert result["stdout"] == ""
    assert result["stderr"] == ""
    assert result["error"] == "No code provided."


def test_missing_e2b_api_key_returns_skipped(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    result = run_python_in_sandbox("print('hello')")

    assert_sandbox_response(result)
    assert result["status"] == "skipped"
    assert result["stdout"] == ""
    assert result["stderr"] == ""
    assert result["error"] == "E2B_API_KEY is not set."


def test_missing_e2b_import_returns_error(monkeypatch):
    def raise_import_error(module_name):
        raise ImportError(f"No module named {module_name}")

    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setattr(sandbox_module.importlib, "import_module", raise_import_error)

    result = run_python_in_sandbox("print('hello')")

    assert_sandbox_response(result)
    assert result["status"] == "error"
    assert result["stdout"] == ""
    assert result["stderr"] == ""
    assert "Failed to import e2b_code_interpreter" in result["error"]


def test_successful_fake_sandbox_returns_stdout(monkeypatch):
    class FakeSandbox:
        def __init__(self, api_key):
            self.api_key = api_key

        def run_code(self, code):
            return SimpleNamespace(
                logs=SimpleNamespace(stdout=["hello\n"], stderr=[]),
                error=None,
            )

        def close(self):
            pass

    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setattr(
        sandbox_module.importlib,
        "import_module",
        lambda module_name: SimpleNamespace(Sandbox=FakeSandbox),
    )

    result = run_python_in_sandbox("print('hello')")

    assert_sandbox_response(result)
    assert result["status"] == "success"
    assert result["stdout"] == "hello\n"
    assert result["stderr"] == ""
    assert result["error"] is None
