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

# 有內建 mock 資料的城市 → 走離線 mock（demo 穩定、零網路）。
# 其他城市（例如台南）→ 走即時抓取（USE_LIVE_SPOT 開啟時）。
SPOTS_BY_CITY = {"台中": TAICHUNG_SPOTS, "臺中": TAICHUNG_SPOTS}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_ALLOWED_SPOT_TYPES = {"outdoor", "indoor", "semi_indoor"}

SPOT_LIVE_SYSTEM_PROMPT = """你是台灣在地旅遊景點規劃專員。根據使用者提供的『目的地城市、旅遊偏好、天數、戶外風險、可選的網路搜尋摘要』，推薦 5~6 個當地『真實存在、知名』的景點。

嚴格要求：
1. 只推薦該目的地城市實際存在的景點，不要杜撰，也不要出現其他城市的景點。
2. 依偏好挑選（例如：美食→夜市或在地小吃聚落；文青→老屋、文創聚落、獨立書店）。
3. 若戶外風險為 high，多安排室內或半室內景點。
4. 只輸出 JSON，不要任何多餘文字或說明。格式為 JSON 陣列，每個元素：
   {"name": str, "type": "outdoor|indoor|semi_indoor", "area": str, "estimated_cost": int（新台幣，免費填 0）, "duration_minutes": int, "reason": str（繁體中文，說明為何推薦）}"""


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

    ranked = sorted(
        TAICHUNG_SPOTS,
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


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUE_VALUES


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def _extract_json(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _tavily_spot_snippets(destination: str, preference: str) -> str:
    """Best-effort：用 Tavily 搜尋當地景點摘要，供 LLM 佐證；失敗回空字串（不致命）。"""
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        return ""
    try:
        query = f"{destination} 熱門景點 推薦 {preference}".strip()
        body = json.dumps({
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
        }).encode("utf-8")
        request = Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = payload.get("results")
        if not isinstance(results, list):
            return ""
        return " ".join(
            str(item.get("content", ""))[:400]
            for item in results[:5]
            if isinstance(item, dict)
        )
    except Exception:
        return ""


def _normalize_spot(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    spot_type = str(raw.get("type", "outdoor")).strip().lower()
    if spot_type not in _ALLOWED_SPOT_TYPES:
        spot_type = "outdoor"
    try:
        cost = max(0, int(float(raw.get("estimated_cost", 0) or 0)))
    except (TypeError, ValueError):
        cost = 0
    try:
        duration = int(float(raw.get("duration_minutes", 90) or 90))
    except (TypeError, ValueError):
        duration = 90
    duration = min(max(duration, 30), 240)
    return {
        "name": name,
        "type": spot_type,
        "area": str(raw.get("area", "")).strip() or "市區",
        "estimated_cost": cost,
        "duration_minutes": duration,
        "reason": str(raw.get("reason", "")).strip() or "符合旅遊偏好的推薦景點。",
    }


def fetch_live_spot_result(state: AgentState, destination: str) -> dict[str, Any]:
    """即時抓取非內建城市的景點：（可選）Tavily 搜尋佐證 + LLM 結構化輸出。"""
    if not _using_mock_llm() and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise ValueError("LLM API key not configured")

    preference = str(_state_value(state, "preference", default=""))
    days = int(_state_value(state, "days", default=2) or 2)
    weather_result = state.get("weather_result", {})  # type: ignore[typeddict-item]
    outdoor_risk = ""
    if isinstance(weather_result, dict):
        outdoor_risk = str(weather_result.get("outdoor_risk", "")).strip()

    grounding = _tavily_spot_snippets(destination, preference)
    context = {
        "destination": destination,
        "preference": preference,
        "days": days,
        "outdoor_risk": outdoor_risk or "unknown",
        "web_reference": grounding[:2000] if grounding
        else "（無外部搜尋結果，請依你對當地的了解推薦真實存在的知名景點）",
    }

    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("SPOT_MODEL", os.getenv("LLM_MODEL", "openai/gpt-4o-mini")),
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore[arg-type]
    )
    response = llm.invoke([
        SystemMessage(content=SPOT_LIVE_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
    ])

    parsed = json.loads(_extract_json(str(response.content)))
    if isinstance(parsed, dict):
        parsed = parsed.get("spots", parsed.get("results", []))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("live spot response is not a non-empty JSON array")

    spots = [spot for spot in (_normalize_spot(raw) for raw in parsed) if spot]
    if not spots:
        raise ValueError("no valid spots after normalization")

    spots.sort(
        key=lambda spot: _score_spot(spot, preference, outdoor_risk or "low"),
        reverse=True,
    )
    spots = spots[: (5 if days >= 2 else 3)]

    return {
        "destination": destination,
        "spots": spots,
        "ticket_cost_total": sum(int(spot.get("estimated_cost", 0)) for spot in spots),
        "recommendation": "以符合偏好且真實存在的景點為主，並依天氣風險調整室內外比例。",
        "source": "live_llm_tavily" if grounding else "live_llm",
        "source_detail": (
            f"由 LLM 即時產生 {destination} 景點"
            + ("，並以 Tavily 搜尋結果佐證。" if grounding else "（未使用外部搜尋佐證）。")
        ),
    }


def spot_node(state: AgentState) -> dict[str, Any]:
    destination = str(_state_value(state, "destination", default="台中") or "台中")

    # 1) 內建 mock 資料的城市（台中）→ 直接離線 mock，demo 穩定
    if destination in SPOTS_BY_CITY:
        return {
            "spot_result": build_mock_spot_result(state),
            "current_task": "spot",
            "next_step": "booking",
        }

    # 2) 其他城市（台南…）→ 即時抓取（需 USE_LIVE_SPOT=1）
    errors: list[str] = []
    if _env_enabled("USE_LIVE_SPOT"):
        try:
            live_result = fetch_live_spot_result(state, destination)
            return {
                "spot_result": live_result,
                "execution_status": "success",
                "error_traceback": "",
                "current_task": "spot",
                "next_step": "booking",
            }
        except Exception as exc:
            errors.append(f"Live spot fetch failed: {exc}")

    # 3) 即時抓取未啟用或失敗 → 退回 mock 樣本，確保 pipeline 不中斷
    fallback = build_mock_spot_result(state)
    reason = "; ".join(errors) or "USE_LIVE_SPOT 未啟用"
    fallback["source"] = "mock_fallback"
    fallback["source_detail"] = (
        f"{destination} 無內建景點資料且即時抓取未啟用/失敗（{reason}），暫以台中樣本示意。"
    )
    return {
        "spot_result": fallback,
        "execution_status": "fallback",
        "error_traceback": reason,
        "current_task": "spot",
        "next_step": "booking",
    }
