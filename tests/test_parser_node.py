import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.parser_worker import parser_node


def make_state(
    route: str = "weather",
    current_task: str = "",
    next_step: str = "",
    sandbox_stdout: str = "",
    execution_status: str = "success",
    error_traceback: str = "",
):
    return {
        "messages": [HumanMessage(content="parse sandbox output")],
        "user_query": "parse sandbox output",
        "route": route,
        "current_task": current_task,
        "next_step": next_step,
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "generated_code": "print('{}')",
        "sandbox_stdout": sandbox_stdout,
        "sandbox_stderr": "",
        "error_traceback": error_traceback,
        "critic_result": None,
        "execution_status": execution_status,
        "retry_count": 0,
        "final_answer": "",
    }


def test_parser_node_writes_weather_result():
    payload = {
        "location": "Taipei",
        "condition": "rainy",
        "rain_probability": 80,
        "temperature": 28,
    }

    result = parser_node(
        make_state(route="weather", sandbox_stdout=json.dumps(payload))
    )

    assert result["execution_status"] == "success"
    assert result["weather_result"] == payload
    assert result["error_traceback"] == ""
    assert "movie_result" not in result
    assert "travel_result" not in result


def test_parser_node_writes_movie_result():
    payload = {
        "title": "Inception",
        "year": 2010,
        "rating": 8.8,
    }

    result = parser_node(make_state(route="movie", sandbox_stdout=json.dumps(payload)))

    assert result["execution_status"] == "success"
    assert result["movie_result"] == payload
    assert "weather_result" not in result
    assert "travel_result" not in result


def test_parser_node_writes_travel_result_from_current_task():
    payload = {
        "destination": "Taipei",
        "duration": "1 day",
        "spots": ["Taipei 101"],
        "transportation": "MRT",
    }

    result = parser_node(
        make_state(
            route="unknown",
            current_task="travel",
            sandbox_stdout=json.dumps(payload),
        )
    )

    assert result["execution_status"] == "success"
    assert result["travel_result"] == payload
    assert "weather_result" not in result
    assert "movie_result" not in result


def test_parser_node_invalid_json_returns_error_traceback():
    result = parser_node(make_state(route="weather", sandbox_stdout="{not json"))

    assert result["execution_status"] == "error"
    assert "JSONDecodeError" in result["error_traceback"]
    assert "weather_result" not in result


def test_parser_node_does_not_parse_when_execution_status_is_not_success():
    result = parser_node(
        make_state(
            route="weather",
            sandbox_stdout=json.dumps({"location": "Taipei"}),
            execution_status="error",
            error_traceback="Sandbox failed.",
        )
    )

    assert result == {
        "execution_status": "error",
        "error_traceback": "Sandbox failed.",
    }


def test_parser_node_empty_stdout_returns_error():
    result = parser_node(make_state(route="weather", sandbox_stdout=""))

    assert result["execution_status"] == "error"
    assert result["error_traceback"] == "No sandbox_stdout found."
    assert "weather_result" not in result
