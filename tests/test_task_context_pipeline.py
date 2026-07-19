import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers import coder_worker, sandbox_worker, weather_worker
from agents.workers.coder_worker import coder_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node
from agents.workers.weather_worker import weather_node


def make_state(
    route: str = "weather",
    current_task: str = "",
    next_step: str = "weather",
    sandbox_stdout: str = "",
):
    return {
        "messages": [HumanMessage(content="幫我查台北天氣")],
        "user_query": "幫我查台北天氣",
        "route": route,
        "current_task": current_task,
        "next_step": next_step,
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": sandbox_stdout,
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


def test_weather_agent_returns_structured_result_without_coder_or_sandbox(monkeypatch):
    class FakeWeatherLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return AIMessage(content=json.dumps({
                "destination": "台北",
                "date_range": "日期未指定",
                "condition": "規劃估計：可能有雨",
                "rain_probability": 80,
                "temperature": "24-28°C",
                "outdoor_risk": "high",
                "recommendation": "此為規劃估計，出發前請查證官方預報。",
            }, ensure_ascii=False))

    monkeypatch.setenv("USE_LIVE_WEATHER", "1")
    monkeypatch.setattr(weather_worker, "ChatOpenAI", FakeWeatherLLM)

    state = make_state(route="weather", next_step="weather")

    apply_update(state, weather_node(state))
    assert state["current_task"] == "weather"
    assert state["next_step"] == "spot"
    assert state["execution_status"] == "success"
    assert state["weather_result"]["destination"] == "台北"
    assert state["weather_result"]["source"] == "llm"


def test_parser_does_not_guess_result_when_only_next_step_is_e2b_sandbox():
    state = make_state(
        route="unknown",
        current_task="",
        next_step="e2b_sandbox",
        sandbox_stdout=json.dumps({"location": "Taipei"}),
    )

    result = parser_node(state)

    assert result["execution_status"] == "error"
    assert result["error_traceback"] == "Unable to determine result target."
    assert "weather_result" not in result


def test_coder_node_does_not_overwrite_current_task(monkeypatch):
    generated_code = "print('{\"location\":\"Taipei\"}')"

    class FakeCoderLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content=f"```python\n{generated_code}\n```")

    monkeypatch.setattr(coder_worker, "ChatOpenAI", FakeCoderLLM)
    monkeypatch.setattr(coder_worker.time, "sleep", lambda seconds: None)

    state = make_state(route="weather", current_task="weather", next_step="coder")
    result = coder_node(state)
    apply_update(state, result)

    assert result["next_step"] == "e2b_sandbox"
    assert result["generated_code"] == generated_code
    assert result.get("current_task") != "e2b_sandbox"
    assert state["current_task"] == "weather"


@pytest.mark.parametrize(
    ("task", "result_key"),
    [
        ("weather", "weather_result"),
        ("travel", "travel_result"),
        ("booking", "booking_result"),
        ("budget", "budget_result"),
        ("scheduler", "scheduler_result"),
        ("traffic", "traffic_result"),
    ],
)
def test_parser_maps_supported_coder_tasks(task, result_key):
    payload = {"task": task, "value": "ok"}
    state = make_state(
        route="unknown",
        current_task=task,
        next_step="e2b_sandbox",
        sandbox_stdout=json.dumps(payload),
    )

    result = parser_node(state)

    assert result["execution_status"] == "success"
    assert result[result_key] == payload
