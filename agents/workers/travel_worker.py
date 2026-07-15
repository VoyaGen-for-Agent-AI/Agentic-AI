import json
import os
import re
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from prompts.itinerary_prompt import ITINERARY_SYSTEM_PROMPT


def _extract_json(content: str) -> str:
    markdown_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if markdown_match:
        return markdown_match.group(1).strip()
    return content.strip()


def _last_user_request(state: AgentState) -> str:
    if state.get("user_query"):
        return str(state["user_query"])
    if state.get("messages"):
        return str(state["messages"][0].content)
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
        if day == 1:
            items.append({
                "time": "10:00",
                "place": f"{destination}車站",
                "activity": "抵達與寄放行李",
                "type": "transport",
                "estimated_cost": 0,
                "reason": "先以交通節點作為起點，方便後續移動。",
            })
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

    return {
        "destination": destination,
        "days": day_count,
        "style": "relaxed",
        "schedule": schedule,
        "ticket_cost_total": ticket_cost_total,
        "transport_hint": transport_hint,
        "planning_reason": "根據使用者偏好、景點候選與交通可行性產生。",
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

    return {
        "itinerary_result": parsed,
        "travel_result": parsed,
        "current_task": "travel",
        "next_step": "final_response",
    }


def travel_node(state: AgentState) -> dict[str, Any]:
    return itinerary_node(state)
