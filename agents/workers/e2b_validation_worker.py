import json
import os
from typing import Any

from core import sandbox as sandbox_runner
from core.state import AgentState


def build_validation_code(state: AgentState) -> str:
    payload = {
        "trip_request": state.get("trip_request", {}),
        "traffic_result": state.get("traffic_result", {}),
        "itinerary_result": state.get("itinerary_result", {}) or state.get("travel_result", {}),
        "booking_result": state.get("booking_result", {}),
        "budget_allocation": state.get("budget_allocation", {}),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    return f'''import json

data = json.loads({payload_json!r})
trip = data.get("trip_request") or {{}}
traffic = data.get("traffic_result") or {{}}
itinerary = data.get("itinerary_result") or {{}}
booking = data.get("booking_result") or {{}}
allocation = data.get("budget_allocation") or {{}}
issues = []

segments = traffic.get("segments") or []
directions = {{segment.get("direction") for segment in segments if isinstance(segment, dict)}}
has_round_trip = "outbound" in directions and "return" in directions
if not has_round_trip:
    issues.append({{"type": "missing_return_transport", "severity": "high", "message": "交通規劃缺少去程或回程。"}})

segment_cost_total = sum(int(segment.get("estimated_cost", 0) or 0) for segment in segments if isinstance(segment, dict))
declared_transport_total = int(traffic.get("total_transport_cost", 0) or 0)
transport_cost_consistent = segment_cost_total == declared_transport_total
if not transport_cost_consistent:
    issues.append({{"type": "unreasonable_transport_cost", "severity": "high", "message": "交通總費用與分段費用加總不一致。"}})

for segment in segments:
    if not isinstance(segment, dict):
        continue
    if ("台北" in str(segment.get("from", "")) and "台中" in str(segment.get("to", ""))
            and "高鐵" in str(segment.get("mode", "")) and int(segment.get("estimated_cost", 0) or 0) < 500):
        issues.append({{"type": "unreasonable_transport_cost", "severity": "high", "message": "台北到台中高鐵票價估計過低。"}})

hotel = booking.get("recommended_hotel") or {{}}
hotel_price_exists = hotel.get("total_price") is not None
if not hotel_price_exists:
    issues.append({{"type": "missing_field", "severity": "high", "message": "住宿結果缺少 recommended_hotel.total_price。"}})

schedule = itinerary.get("schedule")
expected_days = int(trip.get("days", 0) or 0)
itinerary_days_match = isinstance(schedule, list) and len(schedule) == expected_days
if not isinstance(schedule, list):
    issues.append({{"type": "missing_field", "severity": "high", "message": "行程結果缺少 schedule。"}})
elif not itinerary_days_match:
    issues.append({{"type": "missing_field", "severity": "medium", "message": "行程天數與需求天數不一致。"}})

style = str(itinerary.get("style", ""))
schedule_not_too_rushed = True
if isinstance(schedule, list) and style == "relaxed":
    for day in schedule:
        if isinstance(day, dict) and len(day.get("items") or []) > 4:
            schedule_not_too_rushed = False
            issues.append({{"type": "schedule_too_rushed", "severity": "medium", "message": f"Day {{day.get('day')}} 超過 4 個行程點，與 relaxed 風格不符。"}})

known_cost = declared_transport_total + int(hotel.get("total_price", 0) or 0) + int(itinerary.get("ticket_cost_total", 0) or 0)
total_budget = int(trip.get("total_budget", 0) or 0)
budget_within_limit = not total_budget or known_cost <= total_budget
if not budget_within_limit:
    issues.append({{"type": "budget_risk", "severity": "high", "message": "已知交通、住宿與活動費可能超出總預算。"}})

checks = {{
    "has_round_trip_transport": has_round_trip,
    "transport_cost_consistent": transport_cost_consistent,
    "hotel_price_exists": hotel_price_exists,
    "itinerary_days_match": itinerary_days_match,
    "schedule_not_too_rushed": schedule_not_too_rushed,
    "budget_within_limit": budget_within_limit,
}}
has_high = any(issue["severity"] == "high" for issue in issues)
status = "failed" if has_high else "warning" if issues else "passed"
result = {{
    "validation_status": status,
    "issues": issues,
    "checks": checks,
    "recommendation": "請先修正高風險問題再確認行程。" if has_high else "請留意警告並於出發前再次確認。" if issues else "系統檢查通過，仍建議出發前確認最新資訊。",
    "source": "e2b_sandbox",
}}
print(json.dumps(result, ensure_ascii=False))
'''


def _failed_result(message: str) -> dict[str, Any]:
    return {
        "validation_status": "failed",
        "issues": [{"type": "missing_field", "severity": "high", "message": message}],
        "checks": {},
        "recommendation": "E2B validation failed; workflow continued with rule-based budget.",
        "source": "e2b_sandbox",
    }


def e2b_validation_node(state: AgentState) -> dict[str, Any]:
    generated_code = build_validation_code(state)
    if not (os.getenv("E2B_API_KEY") or "").strip():
        return {
            "generated_code": generated_code,
            "sandbox_stdout": "",
            "sandbox_stderr": "",
            "e2b_validation_result": {
                "validation_status": "skipped",
                "issues": [],
                "checks": {},
                "recommendation": "E2B_API_KEY missing; validation skipped.",
                "source": "e2b_skipped",
            },
            "execution_status": "skipped",
            "error_traceback": "",
            "current_task": "e2b_validation",
            "next_step": "budget",
        }

    sandbox_result = sandbox_runner.run_python_in_sandbox(generated_code)
    stdout = str(sandbox_result.get("stdout") or "")
    stderr = str(sandbox_result.get("stderr") or "")
    try:
        if sandbox_result.get("status") != "success":
            raise ValueError(str(sandbox_result.get("error") or "E2B sandbox execution failed"))
        parsed = json.loads(stdout)
        if not isinstance(parsed, dict):
            raise ValueError("E2B validation stdout must be a JSON object")
        parsed["source"] = "e2b_sandbox"
    except Exception as exc:
        error = str(exc)
        return {
            "generated_code": generated_code,
            "sandbox_stdout": stdout,
            "sandbox_stderr": stderr,
            "e2b_validation_result": _failed_result(error),
            "execution_status": "error",
            "error_traceback": error,
            "current_task": "e2b_validation",
            "next_step": "budget",
        }

    return {
        "generated_code": generated_code,
        "sandbox_stdout": stdout,
        "sandbox_stderr": stderr,
        "e2b_validation_result": parsed,
        "execution_status": "success",
        "error_traceback": "",
        "current_task": "e2b_validation",
        "next_step": "budget",
    }
