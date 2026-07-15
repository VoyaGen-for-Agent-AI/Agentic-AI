import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.critic_worker import critic_node


def make_state(**overrides):
    state = {
        "messages": [],
        "user_query": "critic input",
        "route": "travel",
        "current_task": "travel",
        "next_step": "critic",
        "trip_request": {},
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "itinerary_result": {},
        "booking_result": {},
        "budget_result": {},
        "budget_allocation": {},
        "transport_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "critic_feedback": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }
    state.update(overrides)
    return state


def assert_feedback(result, expected_error_type, expected_should_retry):
    assert result["critic_feedback"]["error_type"] == expected_error_type
    assert result["critic_feedback"]["should_retry"] is expected_should_retry
    assert result["critic_feedback"]["reason"]
    assert result["critic_feedback"]["fix_strategy"]
    assert result["critic_feedback"]["fallback_strategy"]
    assert result["critic_result"] == result["critic_feedback"]
    assert result["next_step"] == "final_response"


def test_critic_invalid_json():
    result = critic_node(
        make_state(
            execution_status="error",
            error_traceback="Invalid itinerary JSON",
        )
    )

    assert_feedback(result, "invalid_json", True)


def test_critic_empty_result():
    result = critic_node(make_state(execution_status="empty_result"))

    assert_feedback(result, "empty_result", False)


def test_critic_rate_limit():
    result = critic_node(
        make_state(
            execution_status="error",
            error_traceback="429 rate-limited by provider",
        )
    )

    assert_feedback(result, "rate_limit", True)


def test_critic_api_error():
    result = critic_node(
        make_state(
            execution_status="error",
            error_traceback="502 provider error from upstream API",
        )
    )

    assert result["critic_feedback"]["error_type"] == "api_error"


def test_critic_over_budget():
    result = critic_node(
        make_state(
            budget_result={"status": "over_budget"},
        )
    )

    assert_feedback(result, "over_budget", False)


def test_critic_unknown_error():
    result = critic_node(make_state())

    assert_feedback(result, "unknown_error", False)
