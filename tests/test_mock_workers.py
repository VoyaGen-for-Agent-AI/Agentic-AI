import sys
from pathlib import Path
import os

from langchain_core.messages import AIMessage, HumanMessage
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.mock_workers import (
    booking_node,
    financial_node,
    safety_node,
    scheduler_node,
    travel_node,
)
from agents.workers.weather_worker import weather_node


def make_state(query: str, next_step: str):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "route": next_step,
        "current_task": "",
        "next_step": next_step,
        "weather_result": {},
        "travel_result": {},
        "booking_result": {},
        "financial_result": {},
        "scheduler_result": {},
        "safety_result": {},
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
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("weather_worker requires OPENAI_API_KEY")

    query = "明天台北天氣如何？"
    result = weather_node(make_state(query, "weather"))

    assert_worker_result(
        result,
        "weather_result",
        {"location", "condition", "rain_probability", "temperature"},
    )


def test_travel_node_returns_state_update():
    query = "幫我安排陽明山一日遊"
    result = travel_node(make_state(query, "travel"))

    assert_worker_result(
        result,
        "travel_result",
        {"destination", "duration", "spots", "transportation"},
    )


def test_booking_node_returns_state_update():
    query = "幫我找台北101附近的住宿"
    result = booking_node(make_state(query, "booking"))

    assert_worker_result(
        result,
        "booking_result",
        {"location", "hotels", "restaurants", "price_comparison"},
    )


def test_financial_node_returns_state_update():
    query = "幫我算一下剩餘預算"
    result = financial_node(make_state(query, "financial"))

    assert_worker_result(
        result,
        "financial_result",
        {"budget_total", "budget_remaining", "currency", "exchange_rate_to_usd"},
    )


def test_scheduler_node_returns_state_update():
    query = "幫我排出最佳行程順序"
    result = scheduler_node(make_state(query, "scheduler"))

    assert_worker_result(
        result,
        "scheduler_result",
        {"itinerary", "total_travel_time_minutes", "algorithm"},
    )


def test_safety_node_returns_state_update():
    query = "檢查一下行程有沒有問題"
    result = safety_node(make_state(query, "safety"))

    assert_worker_result(
        result,
        "safety_result",
        {"status", "issues", "fallback_suggestion"},
    )
