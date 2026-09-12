import json
import os
import re
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from prompts.itinerary_prompt import ITINERARY_SYSTEM_PROMPT


_HOTEL_TYPES = {"accommodation", "hotel", "lodging"}
_ZERO_COST_TYPES = {"transport", "traffic", "food", "meal", "restaurant", *_HOTEL_TYPES}
_CHARGEABLE_ACTIVITY_TYPES = {"activity", "ticket", "outdoor", "indoor"}
_HOTEL_KEYWORDS = ("住宿選擇", "住宿", "飯店", "旅館", "hotel", "accommodation")
_TAICHUNG_FORBIDDEN_PLACES = ("清水斷崖", "太魯閣", "阿里山", "日月潭", "墾丁", "九份", "淡水")
_ITINERARY_KEYS = {"destination", "days", "style", "schedule", "transport_hint", "planning_reason"}


def _extract_json(content: str) -> str:
    markdown_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if markdown_match:
        return markdown_match.group(1).strip()
    return content.strip()


def _last_user_request(state: AgentState) -> str:
    user_query = state.get("user_query")
    if user_query:
        return str(user_query)
    messages = state.get("messages") or []
    if messages:
        return str(messages[0].content)
    return "請規劃台中兩天一夜行程。"


def _trip_context(state: AgentState) -> str:
    fields = {
        "origin": state.get("origin"),
        "departure_station": state.get("departure_station"),
        "destination": state.get("destination"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "days": state.get("days"),
        "nights": state.get("nights"),
        "preference": state.get("preference"),
        "total_budget": state.get("total_budget"),
        "weather_result": state.get("weather_result"),
        "traffic_result": state.get("traffic_result"),
        "booking_result": state.get("booking_result"),
    }
    return "\n".join(f"{key}: {value}" for key, value in fields.items() if value not in (None, "", []))


def _schedule_items(itinerary_result: dict[str, Any]):
    schedule = itinerary_result.get("schedule", [])
    if not isinstance(schedule, list):
        return
    for day in schedule:
        if not isinstance(day, dict):
            continue
        items = day.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                yield item


def validate_itinerary_result(
    itinerary_result: dict[str, Any], state: AgentState
) -> tuple[bool, str]:
    """Reject structural errors, out-of-city Taichung places, and lodging content."""
    destination = str(itinerary_result.get("destination", "")).strip()
    if not destination:
        return False, "destination is required"
    if not isinstance(itinerary_result.get("schedule"), list):
        return False, "schedule is required and must be a list"

    expected_destination = str(state.get("destination") or "").strip()
    if expected_destination and destination != expected_destination:
        return False, f"destination mismatch: expected {expected_destination}, got {destination}"

    for item in _schedule_items(itinerary_result):
        place = str(item.get("place", ""))
        activity = str(item.get("activity", ""))
        text = f"{place} {activity}"
        if destination == "台中":
            for forbidden_place in _TAICHUNG_FORBIDDEN_PLACES:
                if forbidden_place in place:
                    return False, f"台中行程包含不合理景點：{forbidden_place}"
        for keyword in _HOTEL_KEYWORDS:
            if keyword.lower() in text.lower():
                return False, f"行程包含住宿內容：{keyword}"
    return True, "validation passed"


def sanitize_itinerary_result(
    itinerary_result: dict[str, Any], state: AgentState
) -> dict[str, Any]:
    """Normalize LLM output and deterministically recalculate admission/activity cost."""
    cleaned = {key: itinerary_result[key] for key in _ITINERARY_KEYS if key in itinerary_result}
    cleaned_schedule = []
    ticket_cost_total = 0
    validation_notes: list[str] = []

    schedule = itinerary_result.get("schedule", [])
    if not isinstance(schedule, list):
        schedule = []
    for day in schedule:
        if not isinstance(day, dict):
            continue
        cleaned_items = []
        items = day.get("items", [])
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            description = " ".join(str(item.get(key, "")) for key in ("place", "activity", "reason"))
            if item_type in _HOTEL_TYPES or any(
                keyword.lower() in description.lower() for keyword in _HOTEL_KEYWORDS
            ):
                validation_notes.append(f"removed lodging item: {item.get('place') or item.get('activity') or item_type}")
                continue
            try:
                estimated_cost = max(0, int(float(item.get("estimated_cost", 0) or 0)))
            except (TypeError, ValueError):
                estimated_cost = 0
            if "免費" in description or item.get("is_free") is True:
                estimated_cost = 0
            if item_type in _ZERO_COST_TYPES:
                if estimated_cost:
                    validation_notes.append(f"zeroed {item_type} cost: {estimated_cost}")
                estimated_cost = 0
            elif item_type not in _CHARGEABLE_ACTIVITY_TYPES:
                if estimated_cost:
                    validation_notes.append(f"excluded unsupported type cost ({item_type or 'missing'}): {estimated_cost}")
                estimated_cost = 0
            cleaned_item = {
                key: item[key]
                for key in ("time", "place", "activity", "type", "reason")
                if key in item
            }
            cleaned_item["estimated_cost"] = estimated_cost
            cleaned_items.append(cleaned_item)
            if item_type in _CHARGEABLE_ACTIVITY_TYPES:
                ticket_cost_total += estimated_cost
        cleaned_schedule.append({"day": day.get("day"), "items": cleaned_items})

    cleaned["schedule"] = cleaned_schedule
    cleaned["ticket_cost_total"] = ticket_cost_total
    transport_hint = str(cleaned.get("transport_hint", ""))
    places = " ".join(str(item.get("place", "")) for item in _schedule_items(cleaned))
    if "高美濕地" in places and "步行" in transport_hint:
        cleaned["transport_hint"] = "跨區景點請依 Traffic Agent 的交通規劃前往，不假設可由市區步行抵達。"
        validation_notes.append("replaced unrealistic walking transport hint")
    cleaned.update({
        "source": itinerary_result.get("source", "llm"),
        "model": itinerary_result.get("model"),
        "source_detail": itinerary_result.get("source_detail", "Generated by AI Itinerary Agent."),
        "validation_status": "sanitized",
        "validation_notes": validation_notes or ["validation passed; ticket_cost_total recalculated"],
    })
    return cleaned


def build_fallback_itinerary_result(state: AgentState) -> dict[str, Any]:
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    destination = state.get("destination") or (
        trip_request.get("destination") if isinstance(trip_request, dict) else ""
    ) or "台中"
    days = int(state.get("days") or (trip_request.get("days") if isinstance(trip_request, dict) else 2) or 2)
    spot_result = state.get("spot_result", {})  # type: ignore[typeddict-item]
    traffic_result = state.get("traffic_result", {})  # type: ignore[typeddict-item]
    spots = spot_result.get("spots", []) if isinstance(spot_result, dict) else []
    if not spots:
        spots = [
            {
                "name": "審計新村",
                "type": "outdoor",
                "estimated_cost": 0,
                "duration_minutes": 90,
                "reason": "符合戶外景點與不要太趕的偏好。",
            },
            {
                "name": "草悟道",
                "type": "outdoor",
                "estimated_cost": 0,
                "duration_minutes": 80,
                "reason": "市區步行友善，適合輕鬆散步。",
            },
            {
                "name": "國家歌劇院",
                "type": "indoor",
                "estimated_cost": 300,
                "duration_minutes": 90,
                "reason": "可作為午後或雨天備案。",
            },
        ]

    schedule = []
    day_count = max(days, 1)
    for day in range(1, day_count + 1):
        day_spots = spots[day - 1::day_count][:3]
        items = []
        for index, spot in enumerate(day_spots):
            items.append({
                "time": f"{11 + index * 2:02d}:00",
                "place": spot.get("name", ""),
                "activity": f"參觀 {spot.get('name', '')}",
                "type": spot.get("type", ""),
                "estimated_cost": int(spot.get("estimated_cost", 0)),
                "reason": spot.get("reason", ""),
            })
        schedule.append({"day": day, "items": items})

    ticket_cost_total = 0
    if isinstance(spot_result, dict) and spot_result.get("ticket_cost_total") is not None:
        ticket_cost_total = int(spot_result["ticket_cost_total"])
    else:
        ticket_cost_total = sum(int(spot.get("estimated_cost", 0)) for spot in spots)

    transport_hint = "以台中市區公車與步行為主，景點集中避免移動過長。"
    if isinstance(traffic_result, dict) and traffic_result.get("warning"):
        transport_hint = str(traffic_result["warning"])

    result = sanitize_itinerary_result({
        "destination": destination,
        "days": day_count,
        "style": "relaxed",
        "schedule": schedule,
        "ticket_cost_total": ticket_cost_total,
        "transport_hint": transport_hint,
        "planning_reason": "根據使用者偏好、景點候選與交通可行性產生。",
        "source": "mock_fallback",
        "source_detail": "Live itinerary generation unavailable or failed; using fallback itinerary.",
    }, state)
    return {
        **result,
        "source": "mock_fallback",
        "source_detail": "Live itinerary generation unavailable or failed; using fallback itinerary.",
        "validation_status": "fallback",
    }


def _validation_fallback(state: AgentState, reason: str) -> dict[str, Any]:
    fallback = build_fallback_itinerary_result(state)
    return {
        **fallback,
        "source": "mock_fallback",
        "source_detail": "LLM itinerary failed validation; using fallback itinerary.",
        "validation_status": "fallback",
        "validation_notes": [reason],
    }


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def itinerary_node(state: AgentState) -> dict[str, Any]:
    print("[Itinerary Agent] 正在產生行程規劃...")

    if (
        not _using_mock_llm()
        and (
            os.getenv("USE_LIVE_ITINERARY") != "1"
            or not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
        )
    ):
        fallback = build_fallback_itinerary_result(state)
        return {
            "itinerary_result": fallback,
            "travel_result": fallback,
            "execution_status": "fallback",
            "error_traceback": "Live itinerary disabled or API key not configured; using fallback itinerary.",
            "current_task": "travel",
            "next_step": "budget",
        }

    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("ITINERARY_MODEL", os.getenv("LLM_MODEL", "openrouter/free")),
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore
    )

    messages = [
        SystemMessage(content=ITINERARY_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"使用者需求：{_last_user_request(state)}\n\n"
                f"已解析旅遊欄位：\n{_trip_context(state)}"
            )
        ),
    ]

    try:
        response = llm.invoke(messages)
        parsed = json.loads(_extract_json(str(response.content)))
        if not isinstance(parsed, dict):
            raise ValueError("Itinerary JSON must be an object")
    except (JSONDecodeError, TypeError, ValueError):
        if _using_mock_llm():
            return {
                "execution_status": "error",
                "error_traceback": "Invalid itinerary JSON",
                "current_task": "travel",
                "next_step": "FINISH",
            }
        fallback = build_fallback_itinerary_result(state)
        return {
            "itinerary_result": fallback,
            "travel_result": fallback,
            "execution_status": "fallback",
            "error_traceback": "Invalid itinerary JSON",
            "current_task": "travel",
            "next_step": "budget",
        }
    except Exception as exc:
        fallback = build_fallback_itinerary_result(state)
        return {
            "itinerary_result": fallback,
            "travel_result": fallback,
            "execution_status": "fallback",
            "error_traceback": str(exc),
            "current_task": "travel",
            "next_step": "budget",
        }

    parsed.update({
        "source": "llm",
        "model": os.getenv("LLM_MODEL"),
        "source_detail": "Generated by AI Itinerary Agent.",
    })
    is_valid, validation_reason = validate_itinerary_result(parsed, state)
    if not is_valid:
        fallback = _validation_fallback(state, validation_reason)
        return {
            "itinerary_result": fallback,
            "travel_result": fallback,
            "execution_status": "fallback",
            "error_traceback": validation_reason,
            "current_task": "travel",
            "next_step": "budget",
        }

    sanitized = sanitize_itinerary_result(parsed, state)
    return {
        "itinerary_result": sanitized,
        "travel_result": sanitized,
        "current_task": "travel",
        "next_step": "final_response",
    }


def travel_node(state: AgentState) -> dict[str, Any]:
    return itinerary_node(state)
