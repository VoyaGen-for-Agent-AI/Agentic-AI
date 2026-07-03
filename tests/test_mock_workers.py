import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.mock_workers import movie_node, travel_node, weather_node


def make_state(query: str, next_step: str):
    return {
        "messages": [HumanMessage(content=query)],
        "next_step": next_step,
        "error_traceback": "",
        "retry_count": 0,
    }


def assert_worker_result(result, expected_label: str, expected_query: str):
    assert set(result.keys()) == {"messages"}
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert "[Mock]" in result["messages"][0].content
    assert expected_label in result["messages"][0].content
    assert expected_query in result["messages"][0].content


def test_weather_node_returns_state_update():
    query = "明天台北天氣如何？"
    result = weather_node(make_state(query, "weather"))

    assert_worker_result(result, "[Weather]", query)


def test_movie_node_returns_state_update():
    query = "推薦一部 Netflix 影集"
    result = movie_node(make_state(query, "movie"))

    assert_worker_result(result, "[Movie]", query)


def test_travel_node_returns_state_update():
    query = "幫我安排陽明山一日遊"
    result = travel_node(make_state(query, "travel"))

    assert_worker_result(result, "[Travel]", query)
