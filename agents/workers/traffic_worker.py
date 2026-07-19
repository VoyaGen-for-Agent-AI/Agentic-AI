import json
import os
import re
from typing import Any

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
    result["total_transport_time_minutes"] = sum(segment["duration_minutes"] for segment in result["segments"])
    result["total_transport_cost"] = sum(segment["estimated_cost"] for segment in result["segments"])
    return result


def traffic_node(state: AgentState) -> dict[str, Any]:
    print("[Traffic Agent] 正在產生交通規劃估計...")

    if not _env_enabled("USE_LIVE_TRAFFIC"):
        return _fallback_update(state, "Live traffic disabled; using mock traffic result.")
    if not _using_mock_llm() and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return _fallback_update(state, "Live traffic API key not configured; using mock traffic result.")

    context = {
        "trip_request": state.get("trip_request", {}),
        "origin": _state_value(state, "origin"),
        "departure_station": _state_value(state, "departure_station"),
        "destination": _state_value(state, "destination"),
        "itinerary_result": state.get("itinerary_result", {}),
        "spot_result": state.get("spot_result", {}),
        "preference": _state_value(state, "preference"),
    }
    try:
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
    except Exception as exc:
        return _fallback_update(state, str(exc))

    traffic_result = {
        **parsed,
        "source": "llm",
        "model": os.getenv("LLM_MODEL"),
        "source_detail": "Generated by Traffic Agent.",
    }
    return {
        "traffic_result": traffic_result,
        "execution_status": "success",
        "error_traceback": "",
        "current_task": "traffic",
        "next_step": "travel",
    }
