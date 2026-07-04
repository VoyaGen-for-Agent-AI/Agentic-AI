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
        "movie_result": results.get("movie_result", {}),
        "travel_result": results.get("travel_result", {}),
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


def test_result_formatters_include_sprint_1_routes():
    assert {"weather", "movie", "travel"}.issubset(RESULT_FORMATTERS.keys())


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


def test_movie_result_generates_final_answer():
    result = final_response_node(
        make_state(
            route="movie",
            movie_result={
                "title": "Inception",
                "genre": "sci-fi",
                "rating": 8.8,
                "recommendation_reason": "適合喜歡燒腦劇情的使用者",
            },
        )
    )

    assert_final_response(result)
    assert "Inception" in result["final_answer"]
    assert "sci-fi" in result["final_answer"]


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


def test_empty_result_generates_fallback_answer():
    result = final_response_node(make_state(route="weather"))

    assert_final_response(result)
    assert result["final_answer"] == FALLBACK_ANSWER


def test_current_task_can_select_formatter_when_route_is_unknown():
    result = final_response_node(
        make_state(
            route="unknown",
            current_task="movie",
            movie_result={
                "title": "Inception",
                "genre": "sci-fi",
                "rating": 8.8,
                "recommendation_reason": "適合喜歡燒腦劇情的使用者",
            },
        )
    )

    assert_final_response(result)
    assert "Inception" in result["final_answer"]


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


def test_next_step_movie_can_select_formatter():
    result = final_response_node(
        make_state(
            route="unknown",
            next_step="movie",
            movie_result={
                "title": "Inception",
                "genre": "sci-fi",
                "rating": 8.8,
                "recommendation_reason": "適合喜歡燒腦劇情的使用者",
            },
        )
    )

    assert_final_response(result)
    assert "Inception" in result["final_answer"]


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
