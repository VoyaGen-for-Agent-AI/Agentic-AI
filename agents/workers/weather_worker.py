import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from prompts.weather_prompt import WEATHER_SYSTEM_PROMPT


_TRUE_VALUES = {"1", "true", "yes", "on"}
_REQUIRED_WEATHER_FIELDS = {
    "destination",
    "date_range",
    "condition",
    "rain_probability",
    "temperature",
    "outdoor_risk",
    "recommendation",
}
CITY_COORDS = {
    "台北": (25.0330, 121.5654),
    "新北": (25.0169, 121.4628),
    "桃園": (24.9937, 121.3010),
    "台中": (24.1477, 120.6736),
    "台南": (22.9999, 120.2269),
    "高雄": (22.6273, 120.3014),
    "宜蘭": (24.7021, 121.7378),
    "花蓮": (23.9911, 121.6112),
}


def _state_value(state: AgentState, key: str, default: Any = "") -> Any:
    value = state.get(key)  # type: ignore[arg-type]
    if value not in (None, "", []):
        return value
    trip_request = state.get("trip_request", {})  # type: ignore[typeddict-item]
    if isinstance(trip_request, dict):
        return trip_request.get(key, default)
    return default


def _date_range(state: AgentState) -> str:
    start_date = str(_state_value(state, "start_date", "")).strip()
    end_date = str(_state_value(state, "end_date", "")).strip()
    if start_date and end_date:
        return f"{start_date} ~ {end_date}"
    return start_date or end_date or "日期未指定"


def build_mock_weather_result(state: AgentState) -> dict[str, Any]:
    destination = str(_state_value(state, "destination", "台中") or "台中")
    return {
        "destination": destination,
        "location": destination,
        "date_range": _date_range(state),
        "condition": "多雲時晴",
        "rain_probability": 30,
        "temperature": "26-32°C",
        "outdoor_risk": "low",
        "recommendation": "此為行程規劃估計；適合安排戶外景點，但午後仍建議保留室內備案。",
        "source": "mock_fallback",
        "source_detail": "Live weather generation unavailable or failed; using mock weather result.",
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
        "weather_result": build_mock_weather_result(state),
        "execution_status": "fallback",
        "error_traceback": error,
        "current_task": "weather",
        "next_step": "spot",
    }


def _validate_weather_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("weather_result must be a JSON object")
    missing = sorted(_REQUIRED_WEATHER_FIELDS - result.keys())
    if missing:
        raise ValueError(f"weather_result missing required fields: {', '.join(missing)}")
    if result["outdoor_risk"] not in {"low", "medium", "high"}:
        raise ValueError("outdoor_risk must be low, medium, or high")
    probability = int(result["rain_probability"])
    if not 0 <= probability <= 100:
        raise ValueError("rain_probability must be between 0 and 100")
    result["rain_probability"] = probability
    return result


def fetch_openweather_weather(
    destination: str, start_date: str | None, end_date: str | None
) -> dict[str, Any]:
    if destination not in CITY_COORDS:
        raise ValueError(f"unknown coordinates for destination: {destination}")
    api_key = (os.getenv("OPENWEATHER_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("OPENWEATHER_API_KEY is not configured")

    latitude, longitude = CITY_COORDS[destination]
    query = urlencode({
        "lat": latitude,
        "lon": longitude,
        "appid": api_key,
        "units": "metric",
        "lang": "zh_tw",
    })
    with urlopen(f"https://api.openweathermap.org/data/2.5/forecast?{query}", timeout=10) as response:
        forecast_payload = json.loads(response.read().decode("utf-8"))

    requested_dates = _requested_dates(start_date, end_date)
    forecast_entries = forecast_payload.get("list")
    if not isinstance(forecast_entries, list):
        raise ValueError("OpenWeather forecast response missing list field")
    entries_by_date: dict[date, list[dict[str, Any]]] = {}
    for entry in forecast_entries:
        if not isinstance(entry, dict):
            continue
        try:
            entry_date = datetime.fromisoformat(str(entry["dt_txt"])).date()
        except (KeyError, ValueError):
            continue
        entries_by_date.setdefault(entry_date, []).append(entry)

    if requested_dates and all(requested_date in entries_by_date for requested_date in requested_dates):
        forecast_days = [
            _normalize_forecast_day(requested_date, entries_by_date[requested_date])
            for requested_date in requested_dates
        ]
        max_rain = max(day["rain_probability"] for day in forecast_days)
        min_temp = min(int(day["temperature"].split("-")[0]) for day in forecast_days)
        max_temp = max(int(day["temperature"].split("-")[1].removesuffix("°C")) for day in forecast_days)
        risk = "high" if max_rain >= 70 else "medium" if max_rain >= 40 else "low"
        return {
            "destination": destination,
            "date_range": _format_date_range(start_date, end_date),
            "forecast_days": forecast_days,
            "condition": "；".join(day["condition"] for day in forecast_days),
            "rain_probability": max_rain,
            "temperature": f"{min_temp}-{max_temp}°C",
            "outdoor_risk": risk,
            "recommendation": "已依旅遊日期整理逐日預報；出發前仍請再次確認官方最新預報。",
            "source": "api_openweather_forecast",
            "source_detail": "Fetched from OpenWeather forecast API.",
        }

    with urlopen(f"https://api.openweathermap.org/data/2.5/weather?{query}", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    weather_items = payload.get("weather")
    main_data = payload.get("main")
    if not isinstance(weather_items, list) or not weather_items or not isinstance(main_data, dict):
        raise ValueError("OpenWeather response missing weather or main fields")
    description = str(weather_items[0].get("description") or weather_items[0].get("main") or "未知")
    weather_code = int(weather_items[0].get("id", 800))
    temp_min = round(float(main_data["temp_min"]))
    temp_max = round(float(main_data["temp_max"]))
    rain_probability = 80 if 200 <= weather_code < 600 else 40 if 600 <= weather_code < 700 else 20
    outdoor_risk = "high" if rain_probability >= 70 else "medium" if rain_probability >= 40 else "low"
    limitation = "旅遊日期超出 forecast range，目前顯示即時天氣作為參考。"
    return {
        "destination": destination,
        "date_range": _format_date_range(start_date, end_date),
        "forecast_days": [],
        "condition": description,
        "rain_probability": rain_probability,
        "temperature": f"{temp_min}-{temp_max}°C",
        "outdoor_risk": outdoor_risk,
        "recommendation": f"{limitation} 出發前請再確認旅遊日期的官方預報。",
        "source": "api_openweather_current",
        "source_detail": f"資料取自 OpenWeather API。{limitation}",
    }


def _parse_trip_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", text)
    if not match:
        return None
    month, day = map(int, match.groups())
    candidate = date.today().replace(month=month, day=day)
    return candidate if candidate >= date.today() else candidate.replace(year=candidate.year + 1)


def _requested_dates(start_date: str | None, end_date: str | None) -> list[date]:
    start = _parse_trip_date(start_date)
    end = _parse_trip_date(end_date) or start
    if not start or not end or end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _format_date_range(start_date: str | None, end_date: str | None) -> str:
    if start_date and end_date:
        return f"{start_date} ~ {end_date}"
    return start_date or end_date or "日期未指定"


def _normalize_forecast_day(day: date, entries: list[dict[str, Any]]) -> dict[str, Any]:
    descriptions: list[str] = []
    temperatures_min: list[float] = []
    temperatures_max: list[float] = []
    probabilities: list[int] = []
    for entry in entries:
        weather_items = entry.get("weather", [])
        main_data = entry.get("main", {})
        if weather_items and isinstance(weather_items[0], dict):
            descriptions.append(str(weather_items[0].get("description") or weather_items[0].get("main") or "未知"))
        if isinstance(main_data, dict):
            temperatures_min.append(float(main_data.get("temp_min", main_data.get("temp", 0))))
            temperatures_max.append(float(main_data.get("temp_max", main_data.get("temp", 0))))
        probabilities.append(round(float(entry.get("pop", 0)) * 100))
    if not descriptions or not temperatures_min or not temperatures_max:
        raise ValueError(f"OpenWeather forecast entries incomplete for {day.isoformat()}")
    rain_probability = max(probabilities, default=0)
    risk = "high" if rain_probability >= 70 else "medium" if rain_probability >= 40 else "low"
    condition = Counter(descriptions).most_common(1)[0][0]
    return {
        "date": f"{day.month}/{day.day}",
        "condition": condition,
        "rain_probability": rain_probability,
        "temperature": f"{round(min(temperatures_min))}-{round(max(temperatures_max))}°C",
        "outdoor_risk": risk,
        "recommendation": "降雨風險偏高，建議保留室內備案。" if risk == "high" else "可安排戶外活動，仍請留意最新預報。",
    }


def _generate_llm_weather(state: AgentState) -> dict[str, Any]:
    if not _using_mock_llm() and not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise ValueError("LLM API key not configured")
    context = {
        "trip_request": state.get("trip_request", {}),
        "destination": _state_value(state, "destination"),
        "start_date": _state_value(state, "start_date"),
        "end_date": _state_value(state, "end_date"),
        "preference": _state_value(state, "preference"),
    }
    llm = ChatOpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        model=os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
        api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),  # type: ignore[arg-type]
    )
    response = llm.invoke([
        SystemMessage(content=WEATHER_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)),
    ])
    parsed = _validate_weather_result(json.loads(_extract_json(str(response.content))))
    return {
        **parsed,
        "source": "llm",
        "model": os.getenv("LLM_MODEL"),
        "source_detail": "Generated by Weather Agent.",
    }


def weather_node(state: AgentState) -> dict[str, Any]:
    print("[Weather Agent] 正在產生天氣規劃估計...")

    if not _env_enabled("USE_LIVE_WEATHER"):
        return _fallback_update(state, "Live weather disabled; using mock weather result.")
    errors: list[str] = []
    provider = os.getenv("WEATHER_PROVIDER", "llm").strip().lower()
    if provider == "openweather":
        try:
            weather_result = fetch_openweather_weather(
                str(_state_value(state, "destination", "台中") or "台中"),
                str(_state_value(state, "start_date") or "") or None,
                str(_state_value(state, "end_date") or "") or None,
            )
            return {
                "weather_result": weather_result,
                "execution_status": "success",
                "error_traceback": "",
                "current_task": "weather",
                "next_step": "spot",
            }
        except Exception as exc:
            errors.append(f"OpenWeather failed: {exc}")
    try:
        weather_result = _generate_llm_weather(state)
    except Exception as exc:
        errors.append(f"LLM weather failed: {exc}")
        return _fallback_update(state, "; ".join(errors))
    return {
        "weather_result": weather_result,
        "execution_status": "fallback" if errors else "success",
        "error_traceback": "; ".join(errors),
        "current_task": "weather",
        "next_step": "spot",
    }
