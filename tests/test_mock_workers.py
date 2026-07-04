import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.mock_workers import movie_node, travel_node, weather_node


def make_state(query: str, next_step: str):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "route": next_step,
        "current_task": "",
        "next_step": next_step,
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def assert_worker_result(result, result_key: str, required_keys: set[str]):
    assert "messages" in result
    assert result_key in result
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert "[Mock]" in result["messages"][0].content
    assert isinstance(result[result_key], dict)
    assert required_keys.issubset(result[result_key].keys())


def test_weather_node_returns_state_update():
    query = "明天台北天氣如何？"
    result = weather_node(make_state(query, "weather"))

    assert_worker_result(
        result,
        "weather_result",
        {"location", "condition", "rain_probability", "temperature"},
    )


def test_movie_node_returns_state_update():
    query = "推薦一部 Netflix 影集"
    result = movie_node(make_state(query, "movie"))

    assert_worker_result(
        result,
        "movie_result",
        {"title", "genre", "rating", "recommendation_reason"},
    )


def test_travel_node_returns_state_update():
    query = "幫我安排陽明山一日遊"
    result = travel_node(make_state(query, "travel"))

    assert_worker_result(
        result,
        "travel_result",
        {"destination", "duration", "spots", "transportation"},
    )
