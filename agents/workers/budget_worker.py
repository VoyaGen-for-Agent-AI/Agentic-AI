from typing import Any

from core.state import AgentState


def allocate_budget(total_budget: int, days: int, nights: int, preference: str = "") -> dict:
    ratios = {
        "hotel_budget": 0.40,
        "transport_budget": 0.18,
        "food_budget": 0.27,
        "activity_budget": 0.05,
        "buffer_budget": 0.10,
    }

    if "省錢" in preference or "便宜" in preference:
        ratios["hotel_budget"] = 0.35
        ratios["buffer_budget"] = 0.15
    elif "舒適" in preference or "不要太累" in preference:
        ratios["hotel_budget"] = 0.45
        ratios["food_budget"] = 0.24
        ratios["buffer_budget"] = 0.08

    allocation = {
        key: int(total_budget * ratio)
        for key, ratio in ratios.items()
        if key != "buffer_budget"
    }
    allocation["buffer_budget"] = total_budget - sum(allocation.values())
    return allocation


def _state_value(state: AgentState, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = state.get(key)  # type: ignore[arg-type]
        if value not in (None, "", []):
            return value
    return default


def _to_int(value: Any, fallback: int | None = None) -> int:
    if value in (None, ""):
        if fallback is None:
            raise ValueError
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        if fallback is None:
            raise ValueError
        return fallback


def _ensure_allocation(state: AgentState) -> dict[str, int]:
    allocation = state.get("budget_allocation")  # type: ignore[typeddict-item]
    if isinstance(allocation, dict) and allocation:
        return {key: _to_int(value, 0) for key, value in allocation.items()}

    total_budget = _to_int(_state_value(state, "total_budget", "budget", default=6000))
    days = _to_int(_state_value(state, "days", default=2), 2)
    nights = _to_int(_state_value(state, "nights", default=1), 1)
    preference = str(_state_value(state, "preference", default=""))
    return allocate_budget(total_budget, days, nights, preference)


def calculate_actual_cost(state: AgentState) -> dict[str, Any]:
    total_budget = _to_int(_state_value(state, "total_budget", "budget", default=6000))
    days = _to_int(_state_value(state, "days", default=2), 2)
    nights = max(_to_int(_state_value(state, "nights", default=1), 1), 1)
    allocation = _ensure_allocation(state)
    used_fallbacks: list[str] = []

    booking_result = state.get("booking_result", {})
    recommended_hotel = {}
    if isinstance(booking_result, dict):
        recommended_hotel = booking_result.get("recommended_hotel") or {}

    if isinstance(recommended_hotel, dict) and recommended_hotel.get("total_price") is not None:
        hotel_cost = _to_int(recommended_hotel["total_price"], 0)
    elif isinstance(recommended_hotel, dict) and recommended_hotel.get("price_per_night") is not None:
        hotel_cost = _to_int(recommended_hotel["price_per_night"], 0) * nights
    else:
        hotel_cost = _to_int(allocation.get("hotel_budget"), 2000)
        used_fallbacks.append("hotel_cost")

    transport_result = state.get("transport_result", {})  # type: ignore[typeddict-item]
    if isinstance(transport_result, dict) and transport_result.get("total_transport_cost") is not None:
        transport_cost = _to_int(transport_result["total_transport_cost"], 0)
    else:
        transport_cost = _to_int(allocation.get("transport_budget"), 500)
        used_fallbacks.append("transport_cost")

    planned_food_cost = days * 800
    if allocation.get("food_budget") is not None:
        food_cost = min(planned_food_cost, _to_int(allocation["food_budget"], planned_food_cost))
    else:
        food_cost = planned_food_cost
        used_fallbacks.append("food_cost")

    itinerary_result = state.get("itinerary_result", {})  # type: ignore[typeddict-item]
    if isinstance(itinerary_result, dict) and itinerary_result.get("ticket_cost_total") is not None:
        activity_cost = _to_int(itinerary_result["ticket_cost_total"], 0)
    else:
        activity_cost = _to_int(allocation.get("activity_budget"), 300)
        used_fallbacks.append("activity_cost")

    if allocation.get("buffer_budget") is not None:
        buffer_cost = _to_int(allocation["buffer_budget"], 500)
    else:
        buffer_cost = 500
        used_fallbacks.append("buffer_cost")

    breakdown = {
        "hotel": hotel_cost,
        "transport": transport_cost,
        "food": food_cost,
        "activity": activity_cost,
        "buffer": buffer_cost,
    }
    total_estimated_cost = sum(breakdown.values())

    return {
        "total_budget": total_budget,
        "total_estimated_cost": total_estimated_cost,
        "remaining_budget": total_budget - total_estimated_cost,
        "allocation": allocation,
        "breakdown": breakdown,
        "used_fallbacks": used_fallbacks,
    }


def evaluate_budget(total_budget: int, total_estimated_cost: int) -> dict[str, Any]:
    remaining_budget = total_budget - total_estimated_cost
    if remaining_budget >= total_budget * 0.15:
        status = "comfortable"
    elif remaining_budget >= 0:
        status = "tight"
    else:
        status = "over_budget"

    return {
        "status": status,
        "remaining_budget": remaining_budget,
        "over_budget_amount": abs(remaining_budget) if remaining_budget < 0 else 0,
    }


def generate_budget_suggestion(
    status: str,
    total_budget: int,
    breakdown: dict,
    allocation: dict,
) -> str:
    if status == "comfortable":
        return "目前預算充足，仍保留一定彈性。"
    if status == "tight":
        return "預算可行但偏緊，建議保留彈性或減少部分非必要支出。"

    if breakdown.get("hotel", 0) > allocation.get("hotel_budget", 0):
        return "目前預估超出總預算，建議改選平價住宿或更換住宿區域。"
    if breakdown.get("transport", 0) > allocation.get("transport_budget", 0):
        return "目前預估超出總預算，建議縮短景點距離或改搭大眾運輸。"
    if breakdown.get("activity", 0) > allocation.get("activity_budget", 0):
        return "目前預估超出總預算，建議替換部分付費景點。"
    return "目前預估超出總預算，建議降低餐費或減少預留支出。"


def budget_node(state: AgentState) -> dict[str, Any]:
    try:
        total_budget = _to_int(_state_value(state, "total_budget", "budget", default=6000))
    except ValueError:
        return {
            "execution_status": "error",
            "error_traceback": "Invalid total_budget",
            "current_task": "budget",
            "next_step": "FINISH",
        }

    budget_allocation = _ensure_allocation(state)
    state_for_calculation = {**state, "budget_allocation": budget_allocation}
    cost_result = calculate_actual_cost(state_for_calculation)  # type: ignore[arg-type]
    evaluation = evaluate_budget(total_budget, cost_result["total_estimated_cost"])
    suggestion = generate_budget_suggestion(
        evaluation["status"],
        total_budget,
        cost_result["breakdown"],
        budget_allocation,
    )

    budget_result = {
        "total_budget": total_budget,
        "total_estimated_cost": cost_result["total_estimated_cost"],
        "remaining_budget": evaluation["remaining_budget"],
        "over_budget_amount": evaluation["over_budget_amount"],
        "status": evaluation["status"],
        "allocation": budget_allocation,
        "breakdown": cost_result["breakdown"],
        "suggestion": suggestion,
        "used_fallbacks": cost_result["used_fallbacks"],
    }

    return {
        "budget_result": budget_result,
        "budget_allocation": budget_allocation,
        "current_task": "budget",
        "next_step": "final_response",
    }
