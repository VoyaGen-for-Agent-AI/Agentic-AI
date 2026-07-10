import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import coder_worker
from agents.workers.coder_worker import coder_node


def make_state():
    return {
        "messages": [HumanMessage(content="幫我查台北天氣")],
        "user_query": "幫我查台北天氣",
        "route": "weather",
        "current_task": "weather",
        "next_step": "coder",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": None,
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def test_coder_node_returns_json_printing_generated_code(monkeypatch):
    generated_code = (
        "print('{\"location\":\"Taipei\",\"condition\":\"rainy\","
        "\"temperature\":28,\"rain_probability\":80}')"
    )

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            assert messages[-1].content.endswith("幫我查台北天氣")
            return SimpleNamespace(
                content=f"```python\n{generated_code}\n```"
            )

    monkeypatch.setattr(coder_worker, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(coder_worker.time, "sleep", lambda seconds: None)

    result = coder_node(make_state())

    assert result["next_step"] == "e2b_sandbox"
    assert isinstance(result["generated_code"], str)
    assert result["generated_code"]
    assert "print" in result["generated_code"]

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exec(result["generated_code"], {})

    parsed_stdout = json.loads(stdout.getvalue())
    assert parsed_stdout == {
        "location": "Taipei",
        "condition": "rainy",
        "temperature": 28,
        "rain_probability": 80,
    }


def test_coder_node_handles_llm_error(monkeypatch):
    class FailingChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            raise Exception("mock llm failure")

    monkeypatch.setattr(coder_worker, "ChatOpenAI", FailingChatOpenAI)
    monkeypatch.setattr(coder_worker.time, "sleep", lambda seconds: None)

    state = make_state()
    result = coder_node(state)
    updated_state = {**state, **result}

    assert result["next_step"] == "FINISH"
    assert result["execution_status"] == "error"
    assert "mock llm failure" in result["error_traceback"]
    assert updated_state["current_task"] == "weather"
    assert updated_state["route"] == "weather"
    assert updated_state["retry_count"] == 0
