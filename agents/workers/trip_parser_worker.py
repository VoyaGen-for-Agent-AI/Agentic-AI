import re
from typing import Any

from core.state import AgentState


DEMO_DEFAULTS = {
    "origin": "台北",
    "departure_station": "台北車站",
    "destination": "台中",
    "start_date": "",
    "end_date": "",
    "days": 2,
    "nights": 1,
    "party_size": 1,
    "total_budget": 6000,
    "preference": "不要太趕、戶外景點",
    "hotel_preference": "交通方便",
    "transport_preference": "大眾運輸",
    "needs_booking": True,
    "needs_budget": True,
    "preferred_areas": ["台中車站", "逢甲"],
}

CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
}


def _extract_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    return CHINESE_NUMBERS.get(value, 0)


def _parse_dates(text: str) -> tuple[str, str]:
    match = re.search(r"(\d{1,2}/\d{1,2})\s*(?:[~-]|到|至)\s*(\d{1,2}/\d{1,2})", text)
    if match:
        return match.group(1), match.group(2)
    return str(DEMO_DEFAULTS["start_date"]), str(DEMO_DEFAULTS["end_date"])


def _parse_days_nights(text: str) -> tuple[int, int]:
    match = re.search(r"([一二兩三四五\d]+)\s*天\s*([一二兩三四五\d]+)\s*夜", text)
    if match:
        days = _extract_number(match.group(1))
        nights = _extract_number(match.group(2))
        if days and nights:
            return days, nights
    return int(DEMO_DEFAULTS["days"]), int(DEMO_DEFAULTS["nights"])


def _parse_budget(text: str) -> int:
    match = re.search(r"(?:一人)?(?:總)?預算\s*([0-9,]+)\s*元?", text)
    if match:
        return int(match.group(1).replace(",", ""))
    return int(DEMO_DEFAULTS["total_budget"])


def _parse_origin(text: str) -> str:
    match = re.search(r"從([^()，,]+)", text)
    if match:
        origin = match.group(1).strip()
        if origin:
            return origin
    if "台北車站出發" in text:
        return "台北"
    return str(DEMO_DEFAULTS["origin"])


def _parse_departure_station(text: str) -> str:
    match = re.search(r"([^()，,]+車站)出發", text)
    if match:
        return match.group(1).strip()
    return str(DEMO_DEFAULTS["departure_station"])


def _parse_destination(text: str) -> str:
    match = re.search(r"[去到]([^，,。()\s]+?)(?=[一二兩三四五\d]+\s*天|[，,。()\s]|$)", text)
    if match:
        destination = match.group(1).strip()
        if destination:
            return destination
    return str(DEMO_DEFAULTS["destination"])


def _parse_preference(text: str) -> str:
    preferences: list[str] = []
    for keyword in ("不要太趕", "戶外景點", "舒適", "省錢", "便宜"):
        if keyword in text:
            preferences.append(keyword)
    return "、".join(preferences) or str(DEMO_DEFAULTS["preference"])


def _parse_hotel_preference(text: str) -> str:
    if "交通方便" in text:
        return "交通方便"
    if "住宿" in text:
        return str(DEMO_DEFAULTS["hotel_preference"])
    return ""


def _parse_transport_preference(text: str) -> str:
    if "高鐵" in text:
        return "高鐵"
    if "台鐵" in text:
        return "台鐵"
    if "大眾運輸" in text or "公車" in text:
        return "大眾運輸"
    return str(DEMO_DEFAULTS["transport_preference"])


def parse_trip_request(text: str) -> dict[str, Any]:
    start_date, end_date = _parse_dates(text)
    days, nights = _parse_days_nights(text)
    needs_booking = "住宿" in text or "旅館" in text or "飯店" in text

    return {
        "origin": _parse_origin(text),
        "departure_station": _parse_departure_station(text),
        "destination": _parse_destination(text),
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "nights": nights,
        "party_size": 1,
        "total_budget": _parse_budget(text),
        "preference": _parse_preference(text),
        "hotel_preference": _parse_hotel_preference(text),
        "transport_preference": _parse_transport_preference(text),
        "needs_booking": needs_booking or bool(DEMO_DEFAULTS["needs_booking"]),
        "needs_budget": True,
        "preferred_areas": list(DEMO_DEFAULTS["preferred_areas"]),
    }


def trip_parser_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages", [])
    text = str(messages[-1].content) if messages else str(state.get("user_query", ""))
    trip_request = parse_trip_request(text)

    return {
        "trip_request": trip_request,
        **trip_request,
        "current_task": "trip_parser",
        "next_step": "travel",
    }
