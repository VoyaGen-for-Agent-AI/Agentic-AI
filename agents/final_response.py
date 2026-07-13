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
    if "schedule" in result:
        return format_itinerary_response(result)

    spots = "、".join(result["spots"])
    return (
        f"建議前往 {result['destination']}，行程長度 {result['duration']}，"
        f"景點包含 {spots}，交通方式建議使用 {result['transportation']}。"
    )


def format_itinerary_response(result: dict[str, Any]) -> str:
    lines = [
        "一、行程安排",
        f"目的地：{result.get('destination', '未指定')}",
        f"行程天數：{result.get('days', '')} 天",
    ]

    for day_plan in result.get("schedule", []):
        lines.append(f"Day {day_plan.get('day')}")
        for item in day_plan.get("items", []):
            lines.append(
                f"- {item.get('time', '')} {item.get('place', '')}："
                f"{item.get('activity', '')}。"
                f"安排原因：{item.get('reason', '')}"
            )

    if result.get("transport_hint"):
        lines.append(f"交通提示：{result['transport_hint']}")
    if result.get("planning_reason"):
        lines.append(f"規劃理由：{result['planning_reason']}")

    return "\n".join(lines)


def format_booking_response(result: dict[str, Any]) -> str:
    recommended_hotel = result.get("recommended_hotel")
    if isinstance(recommended_hotel, dict):
        return (
            "住宿建議：\n"
            f"推薦 {recommended_hotel['name']}，位於 {recommended_hotel['area']}，"
            f"約 {recommended_hotel['price_per_night']} 元 / 晚，"
            f"總價 {recommended_hotel['total_price']} 元。\n"
            f"推薦原因：{recommended_hotel['reason']}"
        )

    hotels = result.get("hotels", [])
    restaurants = result.get("restaurants", [])
    price_comparison = result.get("price_comparison", "")
    location = result.get("location", "目的地")
    hotel_names = "、".join(hotels)
    restaurant_names = "、".join(restaurants)
    return f"{location} 周邊推薦住宿：{hotel_names}；推薦餐廳：{restaurant_names}。{price_comparison}。"


def format_budget_response(result: dict[str, Any]) -> str:
    if "total_estimated_cost" in result:
        status_labels = {
            "comfortable": "預算充足",
            "tight": "預算偏緊",
            "over_budget": "已超出預算",
        }
        breakdown = result.get("breakdown", {})
        budget_delta = (
            f"剩餘預算：{result['remaining_budget']} 元"
            if result.get("remaining_budget", 0) >= 0
            else f"超支金額：{result.get('over_budget_amount', abs(result['remaining_budget']))} 元"
        )
        return (
            "預算估算：\n"
            f"總預算：{result['total_budget']} 元\n"
            f"預估總花費：{result['total_estimated_cost']} 元\n"
            f"{budget_delta}\n"
            f"狀態：{status_labels.get(result['status'], result['status'])} ({result['status']})\n\n"
            "花費明細：\n"
            f"住宿：{breakdown.get('hotel', 0)} 元\n"
            f"交通：{breakdown.get('transport', 0)} 元\n"
            f"飲食：{breakdown.get('food', 0)} 元\n"
            f"活動 / 門票：{breakdown.get('activity', 0)} 元\n"
            f"預留金：{breakdown.get('buffer', 0)} 元\n\n"
            f"建議：{result['suggestion']}"
        )

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
    "itinerary": format_itinerary_response,
    "booking": format_booking_response,
    "budget": format_budget_response,
    "scheduler": format_scheduler_response,
    "safety": format_safety_response,
}

RESULT_KEYS = {
    "weather": "weather_result",
    "travel": "travel_result",
    "itinerary": "itinerary_result",
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
    itinerary_result = state.get("itinerary_result", {})
    booking_result = state.get("booking_result", {})
    budget_result = state.get("budget_result", {})
    has_itinerary_result = isinstance(itinerary_result, dict) and bool(itinerary_result)
    has_booking_result = isinstance(booking_result, dict) and bool(booking_result)
    has_budget_result = isinstance(budget_result, dict) and bool(budget_result)

    if has_itinerary_result and (has_booking_result or has_budget_result):
        sections = [format_itinerary_response(itinerary_result)]
        if has_booking_result:
            sections.append(f"二、{format_booking_response(booking_result)}")
        if has_budget_result:
            sections.append(f"三、{format_budget_response(budget_result)}")
        sections.append("四、總結建議\n請依天氣與現場狀況保留彈性，預算則以明細為基準控管。")
        final_answer = "\n\n".join(sections)
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    if has_booking_result and has_budget_result:
        final_answer = (
            f"{format_booking_response(booking_result)}\n\n"
            f"{format_budget_response(budget_result)}"
        )
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

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
