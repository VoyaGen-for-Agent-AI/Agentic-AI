import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers import sandbox_worker
from agents.workers.critic_worker import critic_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node


def make_state():
    return {
        "messages": [HumanMessage(content="幫我查台北天氣")],
        "user_query": "幫我查台北天氣",
        "route": "weather",
        "current_task": "",
        "next_step": "weather",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": "print('{\"location\":\"Taipei\"}')",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def apply_update(state, update):
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]
    return state


def test_execution_pipeline_generates_weather_final_answer(monkeypatch):
    def fake_run_python_in_sandbox(code):
        assert code == "print('{\"location\":\"Taipei\"}')"
        return {
            "status": "success",
            "stdout": "{\"location\":\"Taipei\",\"condition\":\"rainy\",\"temperature\":28,\"rain_probability\":80}",
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )
    state = make_state()

    apply_update(state, sandbox_node(state))
    assert state["execution_status"] == "success"
    assert state["sandbox_stdout"]

    apply_update(state, parser_node(state))
    assert state["execution_status"] == "success"
    assert state["weather_result"]["location"] == "Taipei"

    apply_update(state, final_response_node(state))

    assert state["execution_status"] == "success"
    assert state["weather_result"]
    assert state["final_answer"]
    assert "Taipei" in state["final_answer"] or "天氣" in state["final_answer"]


def test_execution_pipeline_error_goes_to_critic(monkeypatch):
    def fake_run_python_in_sandbox(code):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "NameError: name 'weather' is not defined",
            "error": "Traceback: NameError",
        }

    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )
    state = make_state()

    apply_update(state, sandbox_node(state))
    assert state["execution_status"] == "error"

    apply_update(state, parser_node(state))
    assert state["execution_status"] == "error"
    assert state["weather_result"] == {}

    apply_update(state, critic_node(state))

    assert state["critic_result"]["error_type"] == "NameError"
    assert "NameError" in state["messages"][-1].content
