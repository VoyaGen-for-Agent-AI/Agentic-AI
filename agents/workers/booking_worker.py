from typing import Any

from core.state import AgentState
from data.mock_hotels import TAICHUNG_HOTELS

from agents.workers.budget_worker import allocate_budget


def _state_value(state: AgentState, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = state.get(key)  # type: ignore[arg-type]
        if value not in (None, "", []):
            return value
    return default


def _normalise_areas(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(area) for area in value if area]
    if isinstance(value, str) and value.strip():
        return [area.strip() for area in value.split(",") if area.strip()]
    return ["台中車站", "逢甲"]


def score_hotel(
    hotel: dict[str, Any],
    hotel_budget: int,
    preferred_areas: list[str],
    preference: str,
    nights: int = 1,
) -> int:
    nights = max(int(nights or 1), 1)
    per_night_budget = hotel_budget / nights
    price = int(hotel["price_per_night"])
    score = 0

    if price <= per_night_budget:
        score += 40
    else:
        score -= 20

    if hotel.get("area") in preferred_areas:
        score += 30

    score += int(float(hotel.get("rating", 0)) * 5)

    tags = [str(tag) for tag in hotel.get("tags", [])]
    if preference and any(tag in preference or preference in tag for tag in tags):
        score += 10
    if preference and any(keyword in tags for keyword in ("便宜", "省錢", "平價")) and any(
        keyword in preference for keyword in ("便宜", "省錢")
    ):
        score += 10
    if preference and "舒適" in tags and "舒適" in preference:
        score += 10

    return score


def _build_hotel_candidate(
    hotel: dict[str, Any],
    hotel_budget: int,
    preferred_areas: list[str],
    preference: str,
    nights: int,
) -> dict[str, Any]:
    score = score_hotel(hotel, hotel_budget, preferred_areas, preference, nights)
    price = int(hotel["price_per_night"])
    per_night_budget = hotel_budget / max(nights, 1)
    within_budget = price <= per_night_budget
    preferred_area = hotel["area"] in preferred_areas

    budget_reason = (
        "符合每晚住宿預算"
        if within_budget
        else "超出每晚住宿預算，僅作備選"
    )
    distance_reason = (
        f"位於偏好區域 {hotel['area']}"
        if preferred_area
        else f"位於 {hotel['area']}，不在優先區域但可比較"
    )

    return {
        "name": hotel["name"],
        "area": hotel["area"],
        "price_per_night": price,
        "rating": hotel["rating"],
        "recommendation_score": score,
        "distance_reason": distance_reason,
        "budget_reason": budget_reason,
        "reason": f"{distance_reason}；{budget_reason}；評分 {hotel['rating']}。",
    }


def booking_node(state: AgentState) -> dict[str, Any]:
    destination = _state_value(state, "destination", default="台中")
    total_budget = int(_state_value(state, "total_budget", "budget", default=6000))
    days = int(_state_value(state, "days", default=2))
    nights = int(_state_value(state, "nights", default=1))
    route_points = _state_value(state, "route_points", default=[])
    preferred_areas = _normalise_areas(
        _state_value(state, "preferred_areas", default=route_points)
    )
    preference = str(_state_value(state, "preference", default="交通方便"))

    budget_allocation = state.get("budget_allocation")  # type: ignore[typeddict-item]
    if (
        not isinstance(budget_allocation, dict)
        or not budget_allocation
        or "hotel_budget" not in budget_allocation
    ):
        budget_allocation = allocate_budget(total_budget, days, nights, preference)

    hotel_budget = int(budget_allocation["hotel_budget"])

    hotel_source = TAICHUNG_HOTELS if destination == "台中" else TAICHUNG_HOTELS
    if not hotel_source:
        return {
            "booking_result": {
                "hotels": [],
                "recommended_hotel": None,
            },
            "execution_status": "empty_result",
            "error_traceback": "No hotel candidates found",
            "current_task": "booking",
        }

    candidates = [
        _build_hotel_candidate(
            hotel,
            hotel_budget=hotel_budget,
            preferred_areas=preferred_areas,
            preference=preference,
            nights=nights,
        )
        for hotel in hotel_source
    ]
    candidates.sort(key=lambda hotel: hotel["recommendation_score"], reverse=True)

    top_hotel = candidates[0]
    recommended_hotel = {
        "name": top_hotel["name"],
        "area": top_hotel["area"],
        "price_per_night": top_hotel["price_per_night"],
        "total_price": top_hotel["price_per_night"] * max(nights, 1),
        "rating": top_hotel["rating"],
        "reason": top_hotel["reason"],
    }

    return {
        "booking_result": {
            "hotels": candidates,
            "recommended_hotel": recommended_hotel,
        },
        "budget_allocation": budget_allocation,
        "current_task": "booking",
        "next_step": "final_response",
    }
