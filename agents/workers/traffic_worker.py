import json
import os
import re
from typing import Any
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from prompts.traffic_prompt import TRAFFIC_PROMPT


_TRUE_VALUES = {"1", "true", "yes", "on"}
_REQUIRED_TRAFFIC_FIELDS = {
    "origin",
    "destination",
    "segments",
    "total_transport_time_minutes",
    "total_transport_cost",
    "feasibility",
    "warning",
}
_REQUIRED_SEGMENT_FIELDS = {"from", "to", "mode", "duration_minutes", "estimated_cost", "note"}


def _state_value(state: AgentState, key: str, default: Any = "") -> Any:
    value = state.get(key)  # type: ignore[arg-type]
    if value not in (None, "", []):
        return value
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    if isinstance(trip_request, dict):
        return trip_request.get(key, default)
    return default


def build_mock_traffic_result(state: AgentState) -> dict[str, Any]:
    origin = str(
        _state_value(state, "departure_station")
        or _state_value(state, "origin")
        or "台北車站"
    )
    destination = str(_state_value(state, "destination", "台中") or "台中")
    arrival_station = f"{destination}車站"
    segments = [
        {
            "from": origin,
            "to": arrival_station,
            "mode": "台鐵/高鐵",
            "duration_minutes": 90,
            "estimated_cost": 700,
            "note": "此為規劃估計，實際時間與票價請以營運單位資訊為準。",
        },
        {
            "from": arrival_station,
            "to": "市區景點",
            "mode": "公車/步行",
            "duration_minutes": 30,
            "estimated_cost": 50,
            "note": "此為規劃估計，請依實際景點位置確認接駁方式。",
        },
    ]
    return {
        "origin": origin,
        "destination": destination,
        "segments": segments,
        "total_transport_time_minutes": sum(segment["duration_minutes"] for segment in segments),
        "total_transport_cost": sum(segment["estimated_cost"] for segment in segments),
        "feasibility": "good",
        "warning": "此為行程規劃估計，不代表即時交通；週末尖峰時段建議提早確認班次。",
        "source": "mock_fallback",
        "source_detail": "Live traffic generation unavailable or failed; using mock traffic result.",
    }


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUE_VALUES


def _using_mock_llm() -> bool:
    return not str(getattr(ChatOpenAI, "__module__", "")).startswith("langchain_openai")


def _extract_json(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _fallback_update(state: AgentState, error: str) -> dict[str, Any]:
    return {
        "traffic_result": build_mock_traffic_result(state),
        "execution_status": "fallback",
        "error_traceback": error,
        "current_task": "traffic",
        "next_step": "travel",
    }


def _apply_route_cost_sanity_checks(segments: list[dict[str, Any]]) -> None:
    for segment in segments:
        origin = str(segment.get("from", ""))
        destination = str(segment.get("to", ""))
        mode = str(segment.get("mode", ""))
        cost = int(segment.get("estimated_cost", 0) or 0)
        if "台北" in origin and "台中" in destination and "高鐵" in mode and cost < 500:
            segment["estimated_cost"] = 700
            correction_note = "票價由 rule-based sanity check 修正，實際票價請以官方資訊為準"
            existing_note = str(segment.get("note", "")).strip()
            segment["note"] = f"{existing_note} {correction_note}".strip()


def _validate_traffic_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("traffic_result must be a JSON object")
    missing = sorted(_REQUIRED_TRAFFIC_FIELDS - result.keys())
    if missing:
        raise ValueError(f"traffic_result missing required fields: {', '.join(missing)}")
    if result["feasibility"] not in {"good", "medium", "poor"}:
        raise ValueError("feasibility must be good, medium, or poor")
    if not isinstance(result["segments"], list) or not result["segments"]:
        raise ValueError("segments must be a non-empty list")
    for index, segment in enumerate(result["segments"]):
        if not isinstance(segment, dict):
            raise ValueError(f"segment {index} must be an object")
        segment_missing = sorted(_REQUIRED_SEGMENT_FIELDS - segment.keys())
        if segment_missing:
            raise ValueError(f"segment {index} missing required fields: {', '.join(segment_missing)}")
        segment["duration_minutes"] = max(0, int(segment["duration_minutes"]))
        segment["estimated_cost"] = max(0, int(segment["estimated_cost"]))
    _apply_route_cost_sanity_checks(result["segments"])
    result["total_transport_time_minutes"] = sum(segment["duration_minutes"] for segment in result["segments"])
    result["total_transport_cost"] = sum(segment["estimated_cost"] for segment in result["segments"])
    return result


def fetch_tavily_traffic(
    origin: str, destination: str, trip_request: dict[str, Any]
) -> dict[str, Any]:
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured")

    departure_station = str(trip_request.get("departure_station") or origin)
    query = f"{departure_station} 到 {destination}車站 交通 高鐵 台鐵 客運 時間 票價 最新"
    spots = trip_request.get("spots", [])
    if isinstance(spots, list) and any("高美濕地" in str(spot) for spot in spots):
        query += f"；{destination} 市區 到 高美濕地 交通 公車 時間 最新"
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

    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("Tavily response contains no search results")
    references = [
        {
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
            "snippet": str(item.get("content", ""))[:500],
        }
        for item in raw_results[:5]
        if isinstance(item, dict)
    ]
    combined_text = " ".join(reference["snippet"] for reference in references)
    duration_match = re.search(r"(\d{1,3})\s*(?:分鐘|分|min(?:ute)?s?)", combined_text, re.IGNORECASE)
    cost_match = re.search(r"(?:票價[^\d]{0,12})?(\d{2,5})\s*元", combined_text)
    estimate_applied = not duration_match or not cost_match
    duration = int(duration_match.group(1)) if duration_match else 60
    cost = int(cost_match.group(1)) if cost_match else 700
    mode = "高鐵" if "高鐵" in combined_text else "台鐵" if "台鐵" in combined_text else "大眾運輸"
    note = "根據 Tavily 搜尋結果整理，實際班次與票價請以官方資訊為準。"
    source_detail = "Traffic planning estimate based on Tavily Search results."
    if estimate_applied:
        note += " 搜尋資訊不足，已套用 rule-based 路線估計。"
        source_detail += " Tavily search was used, but a fallback route estimate was applied."
    segment = {
        "from": departure_station,
        "to": f"{destination}車站",
        "mode": mode,
        "direction": "outbound",
        "duration_minutes": duration,
        "estimated_cost": cost,
        "note": note,
    }
    segments = [segment]
    _apply_route_cost_sanity_checks(segments)
    return_segment = {
        "from": segment["to"],
        "to": segment["from"],
        "mode": segment["mode"],
        "direction": "return",
        "duration_minutes": segment["duration_minutes"],
        "estimated_cost": segment["estimated_cost"],
        "note": "回程以相同交通方式估算，實際班次與票價請以官方資訊為準。",
    }
    segments.append(return_segment)
    return {
        "origin": departure_station,
        "destination": destination,
        "segments": segments,
        "total_transport_time_minutes": sum(item["duration_minutes"] for item in segments),
        "total_transport_cost": sum(item["estimated_cost"] for item in segments),
        "feasibility": "good" if duration <= 120 else "medium",
        "warning": "此為 Tavily 搜尋結果整理的交通規劃估計，不是真正即時導航資料。",
        "source": "tavily_search",
        "source_detail": source_detail,
        "references": references,
    }


def _generate_llm_traffic(state: AgentState) -> dict[str, Any]:
    if not _using_mock_llm() and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise ValueError("LLM API key not configured")
    context = {
        "trip_request": state.get("trip_request", {}),
        "origin": _state_value(state, "origin"),
        "departure_station": _state_value(state, "departure_station"),
        "destination": _state_value(state, "destination"),
        "itinerary_result": state.get("itinerary_result", {}),
        "spot_result": state.get("spot_result", {}),
        "preference": _state_value(state, "preference"),
    }
    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore[arg-type]
    )
    response = llm.invoke([
        SystemMessage(content=TRAFFIC_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)),
    ])
    parsed = _validate_traffic_result(json.loads(_extract_json(str(response.content))))
    return {
        **parsed,
        "source": "llm",
        "model": os.getenv("LLM_MODEL"),
        "source_detail": "Generated by Traffic Agent.",
    }


def traffic_node(state: AgentState) -> dict[str, Any]:
    print("[Traffic Agent] 正在產生交通規劃估計...")

    if not _env_enabled("USE_LIVE_TRAFFIC"):
        return _fallback_update(state, "Live traffic disabled; using mock traffic result.")
    errors: list[str] = []
    provider = os.getenv("TRAFFIC_PROVIDER", "llm").strip().lower()
    if provider == "tavily":
        try:
            trip_request = dict(state.get("trip_request", {}))
            spot_result = state.get("spot_result", {})
            if isinstance(spot_result, dict):
                trip_request["spots"] = [spot.get("name", "") for spot in spot_result.get("spots", []) if isinstance(spot, dict)]
            traffic_result = fetch_tavily_traffic(
                str(_state_value(state, "departure_station") or _state_value(state, "origin") or "台北車站"),
                str(_state_value(state, "destination", "台中") or "台中"),
                trip_request,
            )
            return {
                "traffic_result": traffic_result,
                "execution_status": "success",
                "error_traceback": "",
                "current_task": "traffic",
                "next_step": "travel",
            }
        except Exception as exc:
            errors.append(f"Tavily failed: {exc}")
    try:
        traffic_result = _generate_llm_traffic(state)
    except Exception as exc:
        errors.append(f"LLM traffic failed: {exc}")
        return _fallback_update(state, "; ".join(errors))
    return {
        "traffic_result": traffic_result,
        "execution_status": "fallback" if errors else "success",
        "error_traceback": "; ".join(errors),
        "current_task": "traffic",
        "next_step": "travel",
    }
