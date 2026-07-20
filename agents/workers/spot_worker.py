from typing import Any

from core.state import AgentState


TAICHUNG_SPOTS = [
    {
        "name": "審計新村",
        "type": "outdoor",
        "area": "草悟道",
        "estimated_cost": 0,
        "duration_minutes": 90,
        "reason": "符合戶外景點與不要太趕的偏好。",
    },
    {
        "name": "草悟道",
        "type": "outdoor",
        "area": "草悟道",
        "estimated_cost": 0,
        "duration_minutes": 80,
        "reason": "市區步行友善，適合輕鬆散步。",
    },
    {
        "name": "高美濕地",
        "type": "outdoor",
        "area": "清水",
        "estimated_cost": 0,
        "duration_minutes": 120,
        "reason": "適合安排自然景觀與夕陽，但需預留交通時間。",
    },
    {
        "name": "國家歌劇院",
        "type": "indoor",
        "area": "七期",
        "estimated_cost": 300,
        "duration_minutes": 90,
        "reason": "雨天或午後備案佳，也適合欣賞建築。",
    },
    {
        "name": "宮原眼科",
        "type": "semi_indoor",
        "area": "台中車站",
        "estimated_cost": 0,
        "duration_minutes": 60,
        "reason": "靠近台中車站，適合作為抵達後的輕鬆停留點。",
    },
    {
        "name": "逢甲夜市",
        "type": "outdoor",
        "area": "逢甲",
        "estimated_cost": 0,
        "duration_minutes": 120,
        "reason": "晚間餐飲選擇多，適合第一天晚上安排。",
    },
]


def _state_value(state: AgentState, *keys: str, default: Any = None) -> Any:
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    for key in keys:
        value = state.get(key)  # type: ignore[arg-type]
        if value not in (None, "", []):
            return value
        if isinstance(trip_request, dict):
            value = trip_request.get(key)
            if value not in (None, "", []):
                return value
    return default


def _score_spot(spot: dict[str, Any], preference: str, outdoor_risk: str) -> int:
    score = 0
    if spot["type"] == "outdoor" and "戶外" in preference:
        score += 30
    if "不要太趕" in preference and int(spot["duration_minutes"]) <= 90:
        score += 15
    if outdoor_risk == "high" and spot["type"] == "outdoor":
        score -= 40
    if outdoor_risk == "high" and spot["type"] in {"indoor", "semi_indoor"}:
        score += 25
    if spot["area"] in {"台中車站", "草悟道", "逢甲"}:
        score += 10
    return score


def build_mock_spot_result(state: AgentState) -> dict[str, Any]:
    destination = str(_state_value(state, "destination", default="台中"))
    preference = str(_state_value(state, "preference", default="不要太趕、戶外景點"))
    days = int(_state_value(state, "days", default=2))
    weather_result = state.get("weather_result", {})  # type: ignore[typeddict-item]
    outdoor_risk = ""
    if isinstance(weather_result, dict):
        outdoor_risk = str(weather_result.get("outdoor_risk", "low"))
    outdoor_risk = outdoor_risk or "low"

    candidates = TAICHUNG_SPOTS if destination == "台中" else TAICHUNG_SPOTS
    ranked = sorted(
        candidates,
        key=lambda spot: _score_spot(spot, preference, outdoor_risk),
        reverse=True,
    )
    limit = 5 if days >= 2 else 3
    spots = ranked[:limit]

    return {
        "destination": destination,
        "spots": spots,
        "ticket_cost_total": sum(int(spot.get("estimated_cost", 0)) for spot in spots),
        "recommendation": "以戶外、步行可達、節奏輕鬆的景點為主。"
        if outdoor_risk != "high"
        else "天氣風險偏高，優先加入室內或半室內備案。",
        "source": "mock_spot_data",
        "source_detail": "Selected from predefined mock spot dataset.",
    }


def spot_node(state: AgentState) -> dict[str, Any]:
    return {
        "spot_result": build_mock_spot_result(state),
        "current_task": "spot",
        "next_step": "booking",
    }
