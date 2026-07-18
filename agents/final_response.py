import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from core.state import AgentState


def format_weather_response(result: dict[str, Any]) -> str:
    if "outdoor_risk" in result:
        return (
            "天氣建議：\n"
            f"目的地：{result.get('destination') or result.get('location', '未指定')}\n"
            f"天氣：{result.get('condition', '')}\n"
            f"降雨機率：{result.get('rain_probability', '')}%\n"
            f"氣溫：{result.get('temperature', '')}\n"
            f"戶外風險：{result.get('outdoor_risk', '')}\n"
            f"建議：{result.get('recommendation', '')}"
        )
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


def format_spot_response(result: dict[str, Any]) -> str:
    lines = ["景點推薦："]
    for spot in result.get("spots", [])[:5]:
        lines.append(
            f"- {spot.get('name', '')}（{spot.get('type', '')}）："
            f"費用約 {spot.get('estimated_cost', 0)} 元，"
            f"建議停留 {spot.get('duration_minutes', spot.get('estimated_stay_minutes', ''))} 分鐘。"
            f"推薦原因：{spot.get('reason', '')}"
        )
    if result.get("recommendation"):
        lines.append(f"整體建議：{result['recommendation']}")
    if result.get("ticket_cost_total") is not None:
        lines.append(f"活動 / 門票合計：約 {result['ticket_cost_total']} 元")
    return "\n".join(lines)


def format_traffic_response(result: dict[str, Any]) -> str:
    lines = ["交通摘要："]
    for segment in result.get("segments", []):
        lines.append(
            f"- {segment.get('from', '')} → {segment.get('to', '')}："
            f"{segment.get('mode', '')}，約 {segment.get('duration_minutes', 0)} 分鐘，"
            f"約 {segment.get('estimated_cost', 0)} 元。{segment.get('note', '')}"
        )
    lines.append(f"總交通時間：約 {result.get('total_transport_time_minutes', 0)} 分鐘")
    lines.append(f"總交通費：約 {result.get('total_transport_cost', 0)} 元")
    if result.get("feasibility"):
        lines.append(f"可行性：{result['feasibility']}")
    if result.get("warning"):
        lines.append(f"提醒：{result['warning']}")
    return "\n".join(lines)


def format_trip_request_summary(result: dict[str, Any]) -> str:
    if not result:
        return ""

    dates = ""
    if result.get("start_date") or result.get("end_date"):
        dates = f"日期：{result.get('start_date', '')} ~ {result.get('end_date', '')}\n"

    return (
        "需求摘要：\n"
        f"出發地：{result.get('origin', '未指定')}（{result.get('departure_station', '未指定')}）\n"
        f"目的地：{result.get('destination', '未指定')}\n"
        f"{dates}"
        f"天數：{result.get('days', '')} 天 {result.get('nights', '')} 夜\n"
        f"總預算：{result.get('total_budget', '')} 元\n"
        f"偏好：{result.get('preference', '')}"
    )


def format_critic_feedback(result: dict[str, Any]) -> str:
    return (
        "系統診斷：\n"
        f"錯誤類型：{result.get('error_type', 'unknown_error')}\n"
        f"錯誤原因：{result.get('reason', '')}\n"
        f"修復建議：{result.get('fix_strategy', '')}\n"
        f"Fallback 策略：{result.get('fallback_strategy', '')}"
    )


def format_source_summary(state: AgentState) -> str:
    source_map = [
        ("需求解析", state.get("trip_request", {})),
        ("天氣", state.get("weather_result", {})),
        ("景點", state.get("spot_result", {})),
        ("住宿", state.get("booking_result", {})),
        ("交通", state.get("traffic_result", {})),
        ("行程", state.get("itinerary_result", {}) or state.get("travel_result", {})),
        ("預算", state.get("budget_result", {})),
    ]
    lines = ["資料來源摘要："]
    for label, result in source_map:
        if isinstance(result, dict) and result.get("source"):
            lines.append(f"- {label}：{result['source']}")
    return "\n".join(lines) if len(lines) > 1 else ""


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
    "spot": format_spot_response,
    "traffic": format_traffic_response,
    "scheduler": format_scheduler_response,
    "safety": format_safety_response,
}

RESULT_KEYS = {
    "weather": "weather_result",
    "travel": "travel_result",
    "itinerary": "itinerary_result",
    "booking": "booking_result",
    "budget": "budget_result",
    "spot": "spot_result",
    "traffic": "traffic_result",
    "scheduler": "scheduler_result",
    "safety": "safety_result",
}

FALLBACK_ANSWER = "目前無法根據已有結果產生回覆，請提供更明確的任務或稍後再試。"

AGG_ORDER: list[tuple[str, str]] = [
    ("budget", "budget_result"),
    ("weather", "weather_result"),
    ("travel", "travel_result"),
    ("booking", "booking_result"),
    ("traffic", "traffic_result"),
    ("scheduler", "scheduler_result"),
    ("safety", "safety_result"),
]

SECTION_LABELS = {
    "budget": "預算估算",
    "weather": "天氣",
    "travel": "景點",
    "booking": "訂房",
    "traffic": "交通",
    "scheduler": "行程排程",
    "safety": "安全提醒",
}


def _render_result(route: str, result: dict[str, Any]) -> str:
    formatter = RESULT_FORMATTERS.get(route)
    if formatter:
        try:
            return formatter(result)
        except Exception:
            pass
    return json.dumps(result, ensure_ascii=False, indent=2)


def _select_route(state: AgentState) -> str:
    for route in (state.get("route"), state.get("current_task"), state.get("next_step")):
        if route in RESULT_FORMATTERS:
            return route
    return ""


def final_response_node(state: AgentState):
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    itinerary_result = state.get("itinerary_result", {})
    weather_result = state.get("weather_result", {})
    spot_result = state.get("spot_result", {})
    traffic_result = state.get("traffic_result", {})
    booking_result = state.get("booking_result", {})
    budget_result = state.get("budget_result", {})
    critic_feedback = state.get("critic_feedback") or state.get("critic_result") or {}
    has_itinerary_result = isinstance(itinerary_result, dict) and bool(itinerary_result)
    has_weather_result = isinstance(weather_result, dict) and bool(weather_result)
    has_spot_result = isinstance(spot_result, dict) and bool(spot_result)
    has_traffic_result = isinstance(traffic_result, dict) and bool(traffic_result)
    has_booking_result = isinstance(booking_result, dict) and bool(booking_result)
    has_budget_result = isinstance(budget_result, dict) and bool(budget_result)
    has_critic_feedback = isinstance(critic_feedback, dict) and bool(critic_feedback)

    if has_weather_result or has_spot_result or has_traffic_result:
        sections = []
        if isinstance(trip_request, dict) and trip_request:
            sections.append(format_trip_request_summary(trip_request))
        if has_weather_result:
            sections.append(format_weather_response(weather_result))
        if has_spot_result:
            sections.append(format_spot_response(spot_result))
        if has_traffic_result:
            sections.append(format_traffic_response(traffic_result))
        if has_itinerary_result:
            sections.append(format_itinerary_response(itinerary_result))
        if has_booking_result:
            booking_text = format_booking_response(booking_result)
            if not booking_text.startswith("住宿建議"):
                booking_text = f"住宿建議：\n{booking_text}"
            sections.append(booking_text)
        if has_budget_result:
            sections.append(format_budget_response(budget_result))
        sections.append("總結建議：\n本行程以交通方便、戶外景點與不要太趕為原則；實際出發前請再次確認天氣、交通與票價。")
        if has_critic_feedback:
            sections.append(format_critic_feedback(critic_feedback))
        source_summary = format_source_summary(state)
        if source_summary:
            sections.append(source_summary)
        final_answer = "\n\n".join(sections)
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    if has_itinerary_result and (has_booking_result or has_budget_result):
        sections = []
        if isinstance(trip_request, dict) and trip_request:
            sections.append(format_trip_request_summary(trip_request))
        sections.append(format_itinerary_response(itinerary_result))
        if has_booking_result:
            sections.append(f"二、{format_booking_response(booking_result)}")
        if has_budget_result:
            sections.append(f"三、{format_budget_response(budget_result)}")
        sections.append("四、總結建議\n請依天氣與現場狀況保留彈性，預算則以明細為基準控管。")
        if has_critic_feedback:
            sections.append(format_critic_feedback(critic_feedback))
        source_summary = format_source_summary(state)
        if source_summary:
            sections.append(source_summary)
        final_answer = "\n\n".join(sections)
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    if has_booking_result and has_budget_result:
        sections = []
        if isinstance(trip_request, dict) and trip_request:
            sections.append(format_trip_request_summary(trip_request))
        sections.extend([format_booking_response(booking_result), format_budget_response(budget_result)])
        if has_critic_feedback:
            sections.append(format_critic_feedback(critic_feedback))
        source_summary = format_source_summary(state)
        if source_summary:
            sections.append(source_summary)
        final_answer = "\n\n".join(sections)
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    sections: list[str] = []
    tier = state.get("budget_tier")
    if tier:
        sections.append(f"● 預算階層：{tier}")

    for route, state_key in AGG_ORDER:
        result = state.get(state_key)
        if isinstance(result, dict) and result:
            sections.append(f"● {SECTION_LABELS[route]}：{_render_result(route, result)}")

    if sections:
        final_answer = "為您整理本次旅遊規劃結果如下：\n\n" + "\n\n".join(sections)
    else:
        route = _select_route(state)
        result_key = RESULT_KEYS.get(route, "")
        result = state.get(result_key, {}) if result_key else {}
        if route and isinstance(result, dict) and result:
            final_answer = RESULT_FORMATTERS[route](result)
        else:
            final_answer = FALLBACK_ANSWER

    if isinstance(trip_request, dict) and trip_request and final_answer != FALLBACK_ANSWER:
        final_answer = f"{format_trip_request_summary(trip_request)}\n\n{final_answer}"
    if has_critic_feedback:
        if final_answer == FALLBACK_ANSWER:
            final_answer = format_critic_feedback(critic_feedback)
        else:
            final_answer = f"{final_answer}\n\n{format_critic_feedback(critic_feedback)}"
    source_summary = format_source_summary(state)
    if source_summary and final_answer != FALLBACK_ANSWER:
        final_answer = f"{final_answer}\n\n{source_summary}"

    return {
        "final_answer": final_answer,
        "messages": [AIMessage(content=final_answer)],
    }
