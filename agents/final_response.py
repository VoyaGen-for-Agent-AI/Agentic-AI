from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from core.state import AgentState


def format_weather_response(result: dict[str, Any]) -> str:
    return (
        f"{result['location']} 天氣為 {result['condition']}，"
        f"降雨機率 {result['rain_probability']}%，氣溫 {result['temperature']} 度。"
    )


def format_movie_response(result: dict[str, Any]) -> str:
    return (
        f"推薦電影 {result['title']}，類型是 {result['genre']}，"
        f"評分 {result['rating']}。推薦原因：{result['recommendation_reason']}。"
    )


def format_travel_response(result: dict[str, Any]) -> str:
    spots = "、".join(result["spots"])
    return (
        f"建議前往 {result['destination']}，行程長度 {result['duration']}，"
        f"景點包含 {spots}，交通方式建議使用 {result['transportation']}。"
    )


RESULT_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "weather": format_weather_response,
    "movie": format_movie_response,
    "travel": format_travel_response,
}

RESULT_KEYS = {
    "weather": "weather_result",
    "movie": "movie_result",
    "travel": "travel_result",
}

FALLBACK_ANSWER = "目前無法根據已有結果產生回覆，請提供更明確的任務或稍後再試。"


def _select_route(state: AgentState) -> str:
    for route in (state.get("route"), state.get("current_task"), state.get("next_step")):
        if route in RESULT_FORMATTERS:
            return route
    return ""


def final_response_node(state: AgentState):
    route = _select_route(state)
    result_key = RESULT_KEYS.get(route, "")
    result = state.get(result_key, {}) if result_key else {}

    if route and isinstance(result, dict) and result:
        final_answer = RESULT_FORMATTERS[route](result)
    else:
        final_answer = FALLBACK_ANSWER

    return {
        "final_answer": final_answer,
        "messages": [AIMessage(content=final_answer)],
    }
