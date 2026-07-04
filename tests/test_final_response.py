import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import FALLBACK_ANSWER, RESULT_FORMATTERS, final_response_node
from agents.workers.mock_workers import weather_node
from core.state import AgentState


def make_state(route: str = "unknown", current_task: str = "", **results):
    next_step = results.get("next_step", route)
    return {
        "messages": [HumanMessage(content="請幫我處理這個任務")],
        "user_query": "請幫我處理這個任務",
        "route": route,
        "current_task": current_task,
        "next_step": next_step,
        "weather_result": results.get("weather_result", {}),
        "travel_result": results.get("travel_result", {}),
        "booking_result": results.get("booking_result", {}),
        "financial_result": results.get("financial_result", {}),
        "scheduler_result": results.get("scheduler_result", {}),
        "safety_result": results.get("safety_result", {}),
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }


def assert_final_response(result):
    assert "final_answer" in result
    assert "messages" in result
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content == result["final_answer"]


def test_result_formatters_include_all_agent_routes():
    assert {
        "weather", "travel", "booking", "financial", "scheduler", "safety",
    }.issubset(RESULT_FORMATTERS.keys())


def test_weather_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="weather",
            weather_result={
                "location": "Taipei",
                "condition": "rainy",
                "rain_probability": 80,
                "temperature": 28,
            },
        )
    )

    assert_final_response(result)
    assert "Taipei" in result["final_answer"]
    assert "降雨機率 80%" in result["final_answer"]


def test_travel_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="travel",
            travel_result={
                "destination": "Taipei",
                "duration": "1 day",
                "spots": ["Taipei 101", "Chiang Kai-shek Memorial Hall", "Ximending"],
                "transportation": "MRT",
            },
        )
    )

    assert_final_response(result)
    assert "Taipei 101" in result["final_answer"]
    assert "MRT" in result["final_answer"]


def test_booking_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="booking",
            booking_result={
                "location": "Taipei 101",
                "hotels": ["W Hotel Taipei", "Robertson Suites"],
                "restaurants": ["Din Tai Fung", "Shin Yeh"],
                "price_comparison": "住宿均價 NT$3,500/晚，已篩選出評價最高的 2 間",
            },
        )
    )

    assert_final_response(result)
    assert "W Hotel Taipei" in result["final_answer"]
    assert "Din Tai Fung" in result["final_answer"]


def test_financial_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="financial",
            financial_result={
                "budget_total": 20000.0,
                "budget_remaining": 12500.0,
                "currency": "TWD",
                "exchange_rate_to_usd": 0.031,
            },
        )
    )

    assert_final_response(result)
    assert "12500.0" in result["final_answer"]
    assert "USD" in result["final_answer"]


def test_scheduler_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="scheduler",
            scheduler_result={
                "itinerary": ["Taipei 101", "Ximending", "Chiang Kai-shek Memorial Hall"],
                "total_travel_time_minutes": 95,
                "algorithm": "TSP nearest-neighbor",
            },
        )
    )

    assert_final_response(result)
    assert "Taipei 101" in result["final_answer"]
    assert "95 分鐘" in result["final_answer"]


def test_safety_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="safety",
            safety_result={
                "status": "ok",
                "issues": [],
                "fallback_suggestion": "目前行程無異常，若迷路可撥打當地緊急聯絡電話。",
            },
        )
    )

    assert_final_response(result)
    assert "ok" in result["final_answer"]


def test_empty_result_generates_fallback_answer():
    result = final_response_node(make_state(route="weather"))

    assert_final_response(result)
    assert result["final_answer"] == FALLBACK_ANSWER


def test_current_task_can_select_formatter_when_route_is_unknown():
    result = final_response_node(
        make_state(
            route="unknown",
            current_task="booking",
            booking_result={
                "location": "Taipei 101",
                "hotels": ["W Hotel Taipei", "Robertson Suites"],
                "restaurants": ["Din Tai Fung", "Shin Yeh"],
                "price_comparison": "住宿均價 NT$3,500/晚，已篩選出評價最高的 2 間",
            },
        )
    )

    assert_final_response(result)
    assert "W Hotel Taipei" in result["final_answer"]


def test_next_step_weather_can_select_formatter():
    result = final_response_node(
        make_state(
            route="unknown",
            next_step="weather",
            weather_result={
                "location": "Taipei",
                "condition": "rainy",
                "rain_probability": 80,
                "temperature": 28,
            },
        )
    )

    assert_final_response(result)
    assert "Taipei" in result["final_answer"]


def test_next_step_travel_can_select_formatter():
    result = final_response_node(
        make_state(
            route="unknown",
            next_step="travel",
            travel_result={
                "destination": "Taipei",
                "duration": "1 day",
                "spots": ["Taipei 101", "Chiang Kai-shek Memorial Hall", "Ximending"],
                "transportation": "MRT",
            },
        )
    )

    assert_final_response(result)
    assert "Taipei 101" in result["final_answer"]


def test_next_step_scheduler_can_select_formatter():
    result = final_response_node(
        make_state(
            route="unknown",
            next_step="scheduler",
            scheduler_result={
                "itinerary": ["Taipei 101", "Ximending", "Chiang Kai-shek Memorial Hall"],
                "total_travel_time_minutes": 95,
                "algorithm": "TSP nearest-neighbor",
            },
        )
    )

    assert_final_response(result)
    assert "Taipei 101" in result["final_answer"]


def test_worker_routes_to_final_response_without_llm():
    workflow = StateGraph(AgentState)
    workflow.add_node("weather", weather_node)
    workflow.add_node("final_response", final_response_node)
    workflow.set_entry_point("weather")
    workflow.add_edge("weather", "final_response")
    workflow.add_edge("final_response", END)
    app_graph = workflow.compile()

    result = app_graph.invoke(make_state(route="unknown", next_step="weather"))

    assert "weather_result" in result
    assert result["weather_result"]["location"] == "Taipei"
    assert "final_answer" in result
    assert "降雨機率 80%" in result["final_answer"]
