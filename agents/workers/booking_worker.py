import json
import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from data.mock_hotels import TAICHUNG_HOTELS

from agents.workers.budget_worker import allocate_budget


# 有內建 mock 資料的城市 → 走離線 mock；其他城市（台南…）→ USE_LIVE_BOOKING 開啟時即時抓取。
# 只存城市名，實際房源在呼叫時動態讀取 TAICHUNG_HOTELS 全域（可被測試 monkeypatch）。
MOCK_HOTEL_CITIES = {"台中", "臺中"}

_TRUE_VALUES = {"1", "true", "yes", "on"}

BOOKING_LIVE_SYSTEM_PROMPT = """你是台灣在地訂房規劃專員。根據使用者提供的『目的地城市、每晚住宿預算、住宿晚數、住宿偏好』，
推薦 4~5 間該城市『真實或高度貼近真實』的住宿選擇，涵蓋不同價位與區域。

嚴格要求：
1. 住宿需位於該目的地城市，不要出現其他城市的區域名稱。
2. 價格請以新台幣『每晚』整數估計，貼近當地實際行情。
3. 只輸出 JSON，不要任何多餘文字。格式為 JSON 陣列，每個元素：
   {"name": str, "area": str（該城市的區域/商圈）, "price_per_night": int, "rating": float（0~5）, "tags": [str, ...]}"""


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUE_VALUES


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def _extract_json(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _normalize_hotel(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    try:
        price = max(0, int(float(raw.get("price_per_night", 0) or 0)))
    except (TypeError, ValueError):
        price = 0
    if not price:
        return None
    try:
        rating = float(raw.get("rating", 0) or 0)
    except (TypeError, ValueError):
        rating = 0.0
    rating = min(max(rating, 0.0), 5.0)
    tags = raw.get("tags", [])
    if not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    return {
        "name": name,
        "area": str(raw.get("area", "")).strip() or "市區",
        "price_per_night": price,
        "rating": rating,
        "tags": [str(tag) for tag in tags if str(tag).strip()],
    }


def fetch_live_hotels(
    destination: str, hotel_budget: int, nights: int, preference: str
) -> list[dict[str, Any]]:
    """即時抓取非內建城市的住宿候選（LLM 結構化輸出），回傳與 mock 相同 schema 的清單。"""
    if not _using_mock_llm() and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise ValueError("LLM API key not configured")

    per_night_budget = int(hotel_budget / max(int(nights or 1), 1)) if hotel_budget else 0
    context = {
        "destination": destination,
        "per_night_budget": per_night_budget or "未指定",
        "nights": nights,
        "preference": preference,
    }
    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("BOOKING_MODEL", os.getenv("LLM_MODEL", "openai/gpt-4o-mini")),
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore[arg-type]
    )
    response = llm.invoke([
        SystemMessage(content=BOOKING_LIVE_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
    ])

    parsed = json.loads(_extract_json(str(response.content)))
    if isinstance(parsed, dict):
        parsed = parsed.get("hotels", parsed.get("results", []))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("live hotel response is not a non-empty JSON array")

    hotels = [hotel for hotel in (_normalize_hotel(raw) for raw in parsed) if hotel]
    if not hotels:
        raise ValueError("no valid hotels after normalization")
    return hotels


def _resolve_hotels(
    destination: str, hotel_budget: int, nights: int, preference: str
) -> tuple[list[dict[str, Any]], str, str]:
    """回傳 (住宿清單, source, source_detail)。台中走 mock，其他城市視旗標即時抓、失敗退回 mock。"""
    if destination in MOCK_HOTEL_CITIES:
        return (
            TAICHUNG_HOTELS,
            "mock_hotel_data",
            "Ranked from predefined mock hotel dataset using rule-based scoring.",
        )

    errors: list[str] = []
    if _env_enabled("USE_LIVE_BOOKING"):
        try:
            hotels = fetch_live_hotels(destination, hotel_budget, nights, preference)
            if hotels:
                return (
                    hotels,
                    "live_llm",
                    f"由 LLM 即時產生 {destination} 住宿候選，再以 rule-based scoring 排序。",
                )
        except Exception as exc:
            errors.append(str(exc))

    reason = "; ".join(errors) or "USE_LIVE_BOOKING 未啟用"
    return (
        TAICHUNG_HOTELS,
        "mock_fallback",
        f"{destination} 無內建住宿資料且即時抓取未啟用/失敗（{reason}），暫以台中樣本示意。",
    )


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

    hotel_source, hotel_source_tag, hotel_source_detail = _resolve_hotels(
        str(destination), hotel_budget, nights, preference
    )
    if not hotel_source:
        return {
            "booking_result": {
                "hotels": [],
                "recommended_hotel": None,
                "source": "mock_hotel_data",
                "source_detail": "Ranked from predefined mock hotel dataset using rule-based scoring.",
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
            "source": hotel_source_tag,
            "source_detail": hotel_source_detail,
        },
        "budget_allocation": budget_allocation,
        "current_task": "booking",
        "next_step": "final_response",
    }
