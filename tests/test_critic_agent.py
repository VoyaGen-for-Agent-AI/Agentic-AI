import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.critic_worker import critic_node


def make_state(error_traceback: str = "", sandbox_stderr: str = ""):
    return {
        "messages": [HumanMessage(content="critic input")],
        "user_query": "critic input",
        "route": "weather",
        "current_task": "weather",
        "next_step": "critic",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": "print('{}')",
        "sandbox_stdout": "",
        "sandbox_stderr": sandbox_stderr,
        "error_traceback": error_traceback,
        "critic_result": None,
        "execution_status": "error",
        "retry_count": 0,
        "final_answer": "",
    }


def assert_critic_result(result, expected_error_type: str):
    assert "critic_result" in result
    assert result["critic_result"]["error_type"] == expected_error_type
    assert result["critic_result"]["diagnosis"]
    assert result["critic_result"]["suggestion"]
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert expected_error_type in result["messages"][0].content


def test_critic_classifies_module_not_found_error():
    result = critic_node(
        make_state(error_traceback="ModuleNotFoundError: No module named 'requests'")
    )

    assert_critic_result(result, "ModuleNotFoundError")


def test_critic_classifies_syntax_error():
    result = critic_node(make_state(error_traceback="SyntaxError: invalid syntax"))

    assert_critic_result(result, "SyntaxError")


def test_critic_classifies_name_error():
    result = critic_node(make_state(sandbox_stderr="NameError: name 'city' is not defined"))

    assert_critic_result(result, "NameError")


def test_critic_classifies_timeout_error():
    result = critic_node(make_state(error_traceback="TimeoutError: execution timed out"))

    assert_critic_result(result, "TimeoutError")


def test_critic_classifies_timeout_text():
    result = critic_node(make_state(sandbox_stderr="sandbox timeout after 30 seconds"))

    assert_critic_result(result, "TimeoutError")


def test_critic_classifies_json_decode_error():
    result = critic_node(make_state(error_traceback="JSONDecodeError: invalid JSON"))

    assert_critic_result(result, "JSONDecodeError")


def test_critic_classifies_unknown_error():
    result = critic_node(make_state(error_traceback="ValueError: unexpected result"))

    assert_critic_result(result, "unknown")


def test_critic_returns_none_when_no_error():
    result = critic_node(make_state())

    assert_critic_result(result, "none")
