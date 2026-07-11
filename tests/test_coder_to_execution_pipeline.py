import json
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers import coder_worker, sandbox_worker
from agents.workers.coder_worker import coder_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node


def make_state():
    return {
        "messages": [HumanMessage(content="幫我查台北天氣")],
        "user_query": "幫我查台北天氣",
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


def apply_update(state, update):
    messages = update.pop("messages", None)
    state.update(update)
    if messages:
        state["messages"] = [*state.get("messages", []), *messages]
    return state


def test_coder_node_output_flows_to_execution_pipeline(monkeypatch):
    generated_code = """import json
print(json.dumps({
    "location": "Taipei",
    "condition": "rainy",
    "temperature": 28,
    "rain_probability": 80
}, ensure_ascii=False))"""

    expected_stdout = json.dumps(
        {
            "location": "Taipei",
            "condition": "rainy",
            "temperature": 28,
            "rain_probability": 80,
        },
        ensure_ascii=False,
    )

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            assert messages[-1].content.endswith("幫我查台北天氣")
            return SimpleNamespace(content=f"```python\n{generated_code}\n```")

    def fake_run_python_in_sandbox(code):
        assert code == generated_code
        return {
            "status": "success",
            "stdout": expected_stdout,
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(coder_worker, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(coder_worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sandbox_worker.sandbox_runner,
        "run_python_in_sandbox",
        fake_run_python_in_sandbox,
    )

    state = make_state()

    apply_update(state, coder_node(state))
    assert state["next_step"] == "e2b_sandbox"
    assert isinstance(state["generated_code"], str)
    assert state["generated_code"]
    assert "print" in state["generated_code"]

    apply_update(state, sandbox_node(state))
    assert state["execution_status"] == "success"
    assert state["sandbox_stdout"]

    apply_update(state, parser_node(state))
    assert state["execution_status"] == "success"
    assert state["weather_result"]["location"] == "Taipei"
    assert state["weather_result"]["condition"] == "rainy"

    apply_update(state, final_response_node(state))
    assert state["execution_status"] == "success"
    assert state["final_answer"]
    assert "Taipei" in state["final_answer"] or "天氣" in state["final_answer"]
