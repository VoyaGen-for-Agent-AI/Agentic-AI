import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import sandbox_worker
from agents.workers.sandbox_worker import sandbox_node


def make_state(generated_code: str = "print('hello')"):
    return {
        "messages": [HumanMessage(content="run code")],
        "user_query": "run code",
        "route": "weather",
        "current_task": "weather",
        "next_step": "e2b_sandbox",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": generated_code,
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def test_sandbox_node_writes_stdout_and_execution_status(monkeypatch):
    def fake_run_python_in_sandbox(code):
        assert code == "print('hello')"
        return {
            "status": "success",
            "stdout": "hello\n",
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )

    result = sandbox_node(make_state())

    assert result["execution_status"] == "success"
    assert result["sandbox_stdout"] == "hello\n"
    assert result["sandbox_stderr"] == ""
    assert result["error_traceback"] == ""


def test_sandbox_node_returns_error_when_generated_code_missing():
    result = sandbox_node(make_state(generated_code=""))

    assert result == {
        "execution_status": "error",
        "error_traceback": "No generated_code found.",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
    }


def test_sandbox_node_writes_error_traceback(monkeypatch):
    def fake_run_python_in_sandbox(code):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "NameError: name 'x' is not defined",
            "error": "Traceback: NameError",
        }

    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )

    result = sandbox_node(make_state())

    assert result["execution_status"] == "error"
    assert result["sandbox_stdout"] == ""
    assert result["sandbox_stderr"] == "NameError: name 'x' is not defined"
    assert result["error_traceback"] == "Traceback: NameError"


def test_sandbox_node_maps_skipped_to_error(monkeypatch):
    def fake_run_python_in_sandbox(code):
        return {
            "status": "skipped",
            "stdout": "",
            "stderr": "",
            "error": "E2B_API_KEY is not set.",
        }

    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )

    result = sandbox_node(make_state())

    assert result["execution_status"] == "error"
    assert result["error_traceback"] == "E2B_API_KEY is not set."
