import json
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers import coder_worker, sandbox_worker
from agents.workers.coder_worker import coder_node
from agents.workers.parser_worker import parser_node
from agents.workers.sandbox_worker import sandbox_node
from core.state import AgentState


def _make_initial_state() -> dict:
    query = "請查台北天氣，最後用 mock JSON 回覆"
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "route": "unknown",
        "current_task": "",
        "next_step": "",
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


def _build_mock_weather_workflow():
    workflow = StateGraph(AgentState)

    def mock_supervisor_node(state: AgentState):
        assert state["messages"][-1].content == "請查台北天氣，最後用 mock JSON 回覆"
        return {
            "route": "weather",
            "next_step": "weather",
        }

    def mock_weather_node(state: AgentState):
        assert state["next_step"] == "weather"
        return {
            "messages": [AIMessage(content="請產生台北天氣 mock JSON 的 Python code")],
            "current_task": "weather",
            "next_step": "coder",
        }

    workflow.add_node("supervisor", mock_supervisor_node)
    workflow.add_node("weather", mock_weather_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("e2b_sandbox", sandbox_node)
    workflow.add_node("parser", parser_node)
    workflow.add_node("final_response", final_response_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state["next_step"],
        {
            "weather": "weather",
            "FINISH": END,
        },
    )
    workflow.add_conditional_edges(
        "weather",
        lambda state: state.get("next_step", "FINISH"),
        {
            "coder": "coder",
            "FINISH": END,
        },
    )
    workflow.add_conditional_edges(
        "coder",
        lambda state: state.get("next_step", "FINISH"),
        {
            "e2b_sandbox": "e2b_sandbox",
            "FINISH": END,
        },
    )
    workflow.add_edge("e2b_sandbox", "parser")
    workflow.add_edge("parser", "final_response")
    workflow.add_edge("final_response", END)

    return workflow.compile()


def test_full_weather_workflow_with_mock_supervisor(monkeypatch):
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
            assert messages[-1].content.endswith("請產生台北天氣 mock JSON 的 Python code")
            return SimpleNamespace(content=f"```python\n{generated_code}\n```")

    def fake_run_python_in_sandbox(code: str):
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

    app_graph = _build_mock_weather_workflow()
    result = app_graph.invoke(_make_initial_state())

    assert result["route"] == "weather"
    assert result["current_task"] == "weather"
    assert result["generated_code"] == generated_code
    assert result["next_step"] == "e2b_sandbox"
    assert result["sandbox_stdout"] == expected_stdout
    assert result["execution_status"] == "success"
    assert result["weather_result"]["location"] == "Taipei"
    assert result["weather_result"]["condition"] == "rainy"
    assert result["final_answer"]
    assert "Taipei" in result["final_answer"] or "天氣" in result["final_answer"]
