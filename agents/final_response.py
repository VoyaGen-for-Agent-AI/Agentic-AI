import json
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
    hotels = "、".join(result["hotels"])
    restaurants = "、".join(result["restaurants"])
    return (
        f"{result['location']} 周邊推薦住宿：{hotels}；推薦餐廳：{restaurants}。"
        f"{result['price_comparison']}。"
    )


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

# supervisor 收齊所有 stage 結果後，final_response 依此順序彙整成一份完整回覆
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
    """優先用該類別的 formatter；若結果形狀不符（真實 API/coder 產出的 JSON），退回 json.dumps。"""
    formatter = RESULT_FORMATTERS.get(route)
    if formatter:
        try:
            return formatter(result)
        except Exception:
            pass
    return json.dumps(result, ensure_ascii=False, indent=2)


def final_response_node(state: AgentState):
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
        final_answer = FALLBACK_ANSWER

    return {
        "final_answer": final_answer,
        "messages": [AIMessage(content=final_answer)],
    }
