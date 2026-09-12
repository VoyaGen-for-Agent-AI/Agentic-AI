import json
import os
import re
from typing import Any
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

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
_TRUE_VALUES = {"1", "true", "yes", "on"}
_NON_SPOT_KEYWORDS = ("飯店", "旅館", "住宿", "訂房", "機票", "航班", "高鐵時刻", "交通攻略", "租車", "廣告")
_KNOWN_AREAS = {
    "審計新村": "草悟道",
    "草悟道": "草悟道",
    "高美濕地": "清水",
    "國家歌劇院": "七期",
    "宮原眼科": "台中車站",
    "逢甲夜市": "逢甲",
}
SPOTS_BY_CITY = {"台中": TAICHUNG_SPOTS, "臺中": TAICHUNG_SPOTS}
_ALLOWED_LLM_SPOT_TYPES = {"outdoor", "indoor", "semi_indoor"}
SPOT_LIVE_SYSTEM_PROMPT = """你是台灣在地旅遊景點規劃專員。請根據目的地、偏好、天數、天氣風險與搜尋摘要，推薦 5 至 6 個真實存在的當地景點。
只輸出 JSON 陣列，不要 Markdown 或額外文字。每個元素格式：
{"name": str, "type": "outdoor|indoor|semi_indoor", "area": str, "estimated_cost": int, "duration_minutes": int, "reason": str}"""


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


def _infer_spot_type(text: str) -> str:
    rules = (
        ("nature", ("自然", "濕地", "森林", "海岸", "瀑布")),
        ("food", ("美食", "夜市", "市場", "小吃")),
        ("shopping", ("購物", "商圈", "百貨")),
        ("semi_indoor", ("半室內", "園區")),
        ("indoor", ("室內", "博物館", "美術館", "展覽")),
        ("culture", ("文化", "古蹟", "歌劇院", "歷史")),
        ("outdoor", ("戶外", "步道", "公園", "散步")),
    )
    for spot_type, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return spot_type
    return "unknown"


def _extract_spot_name(title: str, destination: str) -> str:
    name = re.split(r"[｜|]", title, maxsplit=1)[0]
    name = re.sub(rf"^{re.escape(destination)}(?:市)?\s*", "", name).strip(" -：:，,")
    name = re.sub(r"(?:景點)?推薦|旅遊攻略|必去景點|景點", "", name).strip(" -：:，,")
    return name


def _extract_cost(text: str) -> int:
    if "免費" in text or "免門票" in text:
        return 0
    match = re.search(r"(?:門票|票價|費用)[^\d]{0,12}(\d{1,5})\s*元", text)
    return max(0, int(match.group(1))) if match else 0


def _default_duration(spot_type: str) -> int:
    if spot_type in {"outdoor", "nature"}:
        return 120
    return 90


def _normalize_tavily_candidates(
    destination: str, results: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    spots: list[dict[str, Any]] = []
    references: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        title = str(result.get("title", "")).strip()
        snippet = str(result.get("content", "")).strip()
        url = str(result.get("url", "")).strip()
        combined = f"{title} {snippet}"
        references.append({"title": title, "url": url, "snippet": snippet[:500]})
        if not title or any(keyword in combined for keyword in _NON_SPOT_KEYWORDS):
            continue
        if destination == "台中" and "台中" not in combined:
            continue
        name = str(result.get("name") or _extract_spot_name(title, destination)).strip()
        dedupe_key = re.sub(r"\s+", "", name).lower()
        if not name or not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        spot_type = str(result.get("type") or _infer_spot_type(combined)).lower()
        allowed_types = {"outdoor", "indoor", "semi_indoor", "food", "culture", "nature", "shopping", "unknown"}
        if spot_type not in allowed_types:
            spot_type = "unknown"
        duration_match = re.search(r"(\d{1,3})\s*分鐘", combined)
        duration = int(duration_match.group(1)) if duration_match else _default_duration(spot_type)
        spots.append({
            "name": name,
            "type": spot_type,
            "area": str(result.get("area") or _KNOWN_AREAS.get(name) or "待確認"),
            "estimated_cost": _extract_cost(combined),
            "duration_minutes": duration,
            "reason": snippet[:160] or f"根據 Tavily 搜尋結果列為 {destination} 景點候選。",
            "source_title": title,
        })
        if len(spots) == 6:
            break
    return spots, references


def fetch_tavily_spots(
    destination: str, preference: str, trip_request: dict[str, Any]
) -> dict[str, Any]:
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured")
    query = f"{destination} 景點推薦 戶外 自然 市區 交通方便"
    if "戶外" in preference:
        query = f"{destination} 戶外景點 自然景觀 散步 兩天一夜 不要太趕 推薦"
    elif "親子" in preference:
        query = f"{destination} 親子景點 室內戶外 推薦"
    elif "美食" in preference:
        query = f"{destination} 美食景點 市場 夜市 推薦"
    request = Request(
        "https://api.tavily.com/search",
        data=json.dumps({
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 8,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Tavily response missing results list")
    spots, references = _normalize_tavily_candidates(destination, results)

    source = "tavily_search"
    if len(spots) < 3:
        source = "tavily_search_with_mock_fallback"
        mock_state: AgentState = {
            "destination": destination,
            "preference": preference,
            "days": trip_request.get("days", 2),
        }
        for mock_spot in build_mock_spot_result(mock_state)["spots"]:
            if len(spots) >= 3:
                break
            if any(spot["name"] == mock_spot["name"] for spot in spots):
                continue
            spots.append({**mock_spot, "source_title": "mock_spot_data"})

    spots = spots[:6]
    return {
        "destination": destination,
        "spots": spots,
        "ticket_cost_total": sum(int(spot.get("estimated_cost", 0)) for spot in spots),
        "recommendation": "依 Tavily 搜尋結果整理景點，請在出發前確認開放時間與票價。",
        "source": source,
        "source_detail": "Selected from Tavily Search results and normalized by Spot Agent.",
        "references": references,
    }


def _extract_json(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _normalize_llm_spot(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    spot_type = str(raw.get("type", "outdoor")).strip().lower()
    if spot_type not in _ALLOWED_LLM_SPOT_TYPES:
        spot_type = "outdoor"
    try:
        cost = max(0, int(float(raw.get("estimated_cost", 0) or 0)))
    except (TypeError, ValueError):
        cost = 0
    try:
        duration = int(float(raw.get("duration_minutes", 90) or 90))
    except (TypeError, ValueError):
        duration = 90
    return {
        "name": name,
        "type": spot_type,
        "area": str(raw.get("area", "")).strip() or "市區",
        "estimated_cost": cost,
        "duration_minutes": min(max(duration, 30), 240),
        "reason": str(raw.get("reason", "")).strip() or "符合旅遊偏好的推薦景點。",
    }


def fetch_live_spot_result(state: AgentState, destination: str) -> dict[str, Any]:
    """Preserve the merged branch's LLM option for cities without built-in mock data."""
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key and str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai"):
        raise ValueError("LLM API key not configured")

    preference = str(_state_value(state, "preference", default=""))
    weather_result = state.get("weather_result", {})
    outdoor_risk = (
        str(weather_result.get("outdoor_risk", "unknown"))
        if isinstance(weather_result, dict)
        else "unknown"
    )
    context = {
        "destination": destination,
        "preference": preference,
        "days": int(_state_value(state, "days", default=2) or 2),
        "outdoor_risk": outdoor_risk,
    }
    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("SPOT_MODEL", os.getenv("LLM_MODEL", "openai/gpt-4o-mini")),
        api_key=api_key,  # type: ignore[arg-type]
    )
    response = llm.invoke([
        SystemMessage(content=SPOT_LIVE_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
    ])
    parsed = json.loads(_extract_json(str(response.content)))
    if isinstance(parsed, dict):
        parsed = parsed.get("spots", parsed.get("results", []))
    if not isinstance(parsed, list):
        raise ValueError("live spot response is not a JSON array")
    spots = [spot for spot in (_normalize_llm_spot(raw) for raw in parsed) if spot]
    if not spots:
        raise ValueError("no valid spots after normalization")
    spots = spots[:6]
    return {
        "destination": destination,
        "spots": spots,
        "ticket_cost_total": sum(int(spot["estimated_cost"]) for spot in spots),
        "recommendation": "以符合偏好且真實存在的景點為主，並依天氣風險調整室內外比例。",
        "source": "live_llm",
        "source_detail": f"由 LLM 即時產生 {destination} 景點。",
    }


def spot_node(state: AgentState) -> dict[str, Any]:
    live_enabled = os.getenv("USE_LIVE_SPOT", "").strip().lower() in _TRUE_VALUES
    provider = os.getenv("SPOT_PROVIDER", "mock").strip().lower()
    if live_enabled and provider == "tavily":
        try:
            trip_request = state.get("trip_request", {})
            if not isinstance(trip_request, dict):
                trip_request = {}
            spot_result = fetch_tavily_spots(
                str(_state_value(state, "destination", default="台中")),
                str(_state_value(state, "preference", default="不要太趕、戶外景點")),
                trip_request,
            )
            return {
                "spot_result": spot_result,
                "execution_status": "success",
                "error_traceback": "",
                "current_task": "spot",
                "next_step": "booking",
            }
        except Exception as exc:
            return {
                "spot_result": build_mock_spot_result(state),
                "execution_status": "fallback",
                "error_traceback": str(exc),
                "current_task": "spot",
                "next_step": "booking",
            }
    destination = str(_state_value(state, "destination", default="台中") or "台中")
    if live_enabled and destination not in SPOTS_BY_CITY:
        try:
            return {
                "spot_result": fetch_live_spot_result(state, destination),
                "execution_status": "success",
                "error_traceback": "",
                "current_task": "spot",
                "next_step": "booking",
            }
        except Exception as exc:
            fallback = build_mock_spot_result(state)
            fallback["source"] = "mock_fallback"
            fallback["source_detail"] = (
                f"{destination} 即時景點產生失敗，暫以 mock 景點示意。"
            )
            return {
                "spot_result": fallback,
                "execution_status": "fallback",
                "error_traceback": str(exc),
                "current_task": "spot",
                "next_step": "booking",
            }
    return {
        "spot_result": build_mock_spot_result(state),
        "current_task": "spot",
        "next_step": "booking",
    }
