from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from core.state import AgentState


def format_weather_response(result: dict[str, Any]) -> str:
    return (
        f"{result['location']} 天氣為 {result['condition']}，"
        f"降雨機率 {result['rain_probability']}%，氣溫 {result['temperature']} 度。"
    )


def format_travel_response(result: dict[str, Any]) -> str:
    spots = "、".join(result["spots"])
    return (
        f"建議前往 {result['destination']}，行程長度 {result['duration']}，"
        f"景點包含 {spots}，交通方式建議使用 {result['transportation']}。"
    )


def format_booking_response(result: dict[str, Any]) -> str:
    recommended_hotel = result.get("recommended_hotel")
    if isinstance(recommended_hotel, dict):
        return (
            f"推薦住宿：{recommended_hotel['name']}，位於 {recommended_hotel['area']}，"
            f"每晚 {recommended_hotel['price_per_night']} 元，"
            f"總價 {recommended_hotel['total_price']} 元。"
            f"{recommended_hotel['reason']}"
        )

    hotels = result.get("hotels", [])
    restaurants = result.get("restaurants", [])
    price_comparison = result.get("price_comparison", "")
    location = result.get("location", "目的地")
    hotel_names = "、".join(hotels)
    restaurant_names = "、".join(restaurants)
    return f"{location} 周邊推薦住宿：{hotel_names}；推薦餐廳：{restaurant_names}。{price_comparison}。"


def format_budget_response(result: dict[str, Any]) -> str:
    return (
        f"總預算 {result['currency']} {result['budget_total']}，"
        f"剩餘可用預算 {result['currency']} {result['budget_remaining']}"
        f"（約合 USD {result['budget_remaining'] * result['exchange_rate_to_usd']:.2f}）。"
    )


def format_scheduler_response(result: dict[str, Any]) -> str:
    itinerary = " → ".join(result["itinerary"])
    return (
        f"最佳行程順序：{itinerary}，"
        f"總移動時間約 {result['total_travel_time_minutes']} 分鐘（{result['algorithm']}）。"
    )


def format_safety_response(result: dict[str, Any]) -> str:
    if result["issues"]:
        issues = "、".join(result["issues"])
        return f"偵測到狀況：{issues}。建議：{result['fallback_suggestion']}"
    return f"行程狀態：{result['status']}。{result['fallback_suggestion']}"


RESULT_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "weather": format_weather_response,
    "travel": format_travel_response,
    "booking": format_booking_response,
    "budget": format_budget_response,
    "scheduler": format_scheduler_response,
    "safety": format_safety_response,
}

RESULT_KEYS = {
    "weather": "weather_result",
    "travel": "travel_result",
    "booking": "booking_result",
    "budget": "budget_result",
    "scheduler": "scheduler_result",
    "safety": "safety_result",
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
