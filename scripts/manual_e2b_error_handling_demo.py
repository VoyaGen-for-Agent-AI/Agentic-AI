"""Standalone E2B sandbox and error-recovery teaching demo.

This script never executes generated validation code on the local machine.
When E2B is unavailable, deterministic sandbox responses are simulated so the
same parsing, critic, and fallback flow can still be demonstrated.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.sandbox import run_python_in_sandbox

load_dotenv()


SandboxRunner = Callable[[str], dict[str, str | None]]
_SENSITIVE_ENV_NAMES = (
    "E2B_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENWEATHER_API_KEY",
    "TAVILY_API_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
)


DEMO_DATA = {
    "trip_request": {"destination": "台中", "days": 2},
    "traffic_result": {
        "segments": [
            {
                "from": "台北車站",
                "to": "台中車站",
                "direction": "outbound",
                "estimated_cost": 700,
            },
            {
                "from": "台中車站",
                "to": "台北車站",
                "direction": "return",
                "estimated_cost": 700,
            },
        ],
        "total_transport_cost": 1400,
    },
    "booking_result": {"recommended_hotel": {"total_price": 2400}},
    "itinerary_result": {
        "schedule": [{"day": 1, "items": []}, {"day": 2, "items": []}]
    },
}


def build_valid_validation_code() -> str:
    payload = json.dumps(DEMO_DATA, ensure_ascii=False)
    return f'''import json

data = json.loads({payload!r})
traffic = data["traffic_result"]
segments = traffic.get("segments", [])
directions = {{item.get("direction") for item in segments}}
checks = {{
    "has_round_trip_transport": {{"outbound", "return"}}.issubset(directions),
    "transport_cost_consistent": traffic.get("total_transport_cost") == sum(
        int(item.get("estimated_cost", 0)) for item in segments
    ),
    "hotel_price_exists": (
        data.get("booking_result", {{}})
        .get("recommended_hotel", {{}})
        .get("total_price") is not None
    ),
    "itinerary_days_match": len(
        data.get("itinerary_result", {{}}).get("schedule", [])
    ) == int(data.get("trip_request", {{}}).get("days", 0)),
}}
issues = [
    {{"type": name, "severity": "high", "message": "Validation check failed."}}
    for name, passed in checks.items() if not passed
]
result = {{
    "validation_status": "passed" if not issues else "failed",
    "issues": issues,
    "checks": checks,
    "recommendation": "Validation passed." if not issues else "Review failed checks.",
    "source": "e2b_sandbox",
}}
print(json.dumps(result, ensure_ascii=False))
'''


CASE_CODES = {
    "valid_code_success": build_valid_validation_code,
    "sandbox_execution_error": lambda: (
        'raise RuntimeError("simulated validation failure")\n'
    ),
    "invalid_json_stdout": lambda: 'print("{bad json")\n',
}


def classify_error(error_context: dict[str, Any]) -> dict[str, str]:
    """Classify the small set of errors used in this teaching flow."""
    requested_type = str(error_context.get("error_type") or "")
    status = str(error_context.get("execution_status") or "")
    detail = " ".join(
        str(error_context.get(key) or "")
        for key in ("stderr", "error_traceback", "message")
    ).lower()

    if requested_type == "invalid_json":
        error_type, severity = "invalid_json", "medium"
        fallback_action = "Use structured parser fallback and continue workflow."
    elif status == "skipped" or "e2b_api_key" in detail:
        error_type, severity = "missing_e2b_key", "medium"
        fallback_action = "Use simulated sandbox result for demo."
    elif "runtimeerror" in detail or "runtime error" in detail:
        error_type, severity = "runtime_error", "high"
        fallback_action = "Use validation fallback and continue workflow."
    elif status in {"error", "timeout"}:
        error_type, severity = "sandbox_execution_error", "high"
        fallback_action = "Use validation fallback and continue workflow."
    else:
        error_type, severity = "unknown_error", "high"
        fallback_action = "Use safe fallback and continue workflow."

    return {
        "error_type": error_type,
        "severity": severity,
        "fallback_action": fallback_action,
    }


def _redact_secrets(value: Any) -> str:
    text = str(value or "")
    for name in _SENSITIVE_ENV_NAMES:
        secret = os.getenv(name) or ""
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _simulated_sandbox_result(case_name: str) -> dict[str, str | None]:
    if case_name == "valid_code_success":
        validation = {
            "validation_status": "passed",
            "issues": [],
            "checks": {
                "has_round_trip_transport": True,
                "transport_cost_consistent": True,
                "hotel_price_exists": True,
                "itinerary_days_match": True,
            },
            "recommendation": "Validation passed.",
            "source": "simulated_e2b",
        }
        return {
            "status": "success",
            "stdout": json.dumps(validation, ensure_ascii=False),
            "stderr": "",
            "error": None,
        }
    if case_name == "sandbox_execution_error":
        error = "RuntimeError: simulated validation failure"
        return {"status": "error", "stdout": "", "stderr": error, "error": error}
    return {
        "status": "success",
        "stdout": "{bad json\n",
        "stderr": "",
        "error": None,
    }


def real_e2b_available(
    sandbox_runner: SandboxRunner = run_python_in_sandbox,
) -> bool:
    """Probe E2B without exposing credentials or confusing code errors with outages."""
    probe = sandbox_runner('print("e2b-demo-ready")')
    return (
        probe.get("status") == "success"
        and "e2b-demo-ready" in str(probe.get("stdout") or "")
    )


def _fallback_validation(error_type: str) -> dict[str, Any]:
    if error_type == "invalid_json":
        return {
            "validation_status": "warning",
            "issues": [{
                "type": "invalid_json",
                "severity": "medium",
                "message": "Sandbox stdout is not valid JSON.",
            }],
            "recommendation": "Use structured fallback result and continue workflow.",
            "source": "parser_fallback",
        }
    issue_type = (
        error_type
        if error_type in {"sandbox_execution_error", "runtime_error"}
        else "sandbox_execution_error"
    )
    return {
        "validation_status": "failed",
        "issues": [{
            "type": issue_type,
            "severity": "high",
            "message": "Generated validation code failed inside sandbox.",
        }],
        "recommendation": "Use fallback validation result and continue workflow.",
        "source": "e2b_error_fallback",
    }


def run_case(
    case_name: str,
    *,
    sandbox_runner: SandboxRunner | None = None,
    use_real_e2b: bool | None = None,
) -> dict[str, Any]:
    if case_name not in CASE_CODES:
        raise ValueError(f"Unknown demo case: {case_name}")

    code = CASE_CODES[case_name]()
    if use_real_e2b is None:
        use_real_e2b = bool((os.getenv("E2B_API_KEY") or "").strip())
    if sandbox_runner is None:
        sandbox_runner = run_python_in_sandbox

    sandbox_result = (
        sandbox_runner(code) if use_real_e2b
        else _simulated_sandbox_result(case_name)
    )
    execution_status = str(sandbox_result.get("status") or "error")
    stdout = _redact_secrets(sandbox_result.get("stdout"))
    stderr = _redact_secrets(sandbox_result.get("stderr"))
    error_traceback = _redact_secrets(sandbox_result.get("error"))
    simulated = not use_real_e2b

    parsed: dict[str, Any] | None = None
    parse_success = False
    critic_result: dict[str, str] | None = None
    try:
        if execution_status != "success":
            raise RuntimeError(error_traceback or stderr or "Sandbox execution failed")
        candidate = json.loads(stdout)
        if not isinstance(candidate, dict):
            raise json.JSONDecodeError("Expected a JSON object", stdout, 0)
        parsed = candidate
        if simulated:
            parsed["source"] = "simulated_e2b"
        parse_success = True
    except json.JSONDecodeError as exc:
        critic_result = classify_error({
            "error_type": "invalid_json",
            "execution_status": execution_status,
            "message": str(exc),
        })
        parsed = _fallback_validation("invalid_json")
    except Exception as exc:
        critic_result = classify_error({
            "execution_status": execution_status,
            "stderr": stderr,
            "error_traceback": error_traceback or str(exc),
        })
        parsed = _fallback_validation(critic_result["error_type"])

    return {
        "case_name": case_name,
        "generated_code": code,
        "execution_status": execution_status,
        "sandbox_stdout": stdout,
        "sandbox_stderr": stderr,
        "error_traceback": error_traceback,
        "sandbox_source": "simulated_e2b" if simulated else "e2b_sandbox",
        "parse_success": parse_success,
        "critic_result": critic_result,
        "validation_result": parsed,
        "workflow_continued": True,
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_case(result: dict[str, Any], index: int) -> None:
    print(f"\n[Case {index}] {result['case_name']}")
    print("Generated validation code:")
    print(result["generated_code"].rstrip())
    print("Running in E2B Sandbox...")
    print(f"execution_status: {result['execution_status']}")
    if result["sandbox_stdout"]:
        print("sandbox_stdout:")
        print(result["sandbox_stdout"].rstrip())
    if result["sandbox_stderr"] or result["error_traceback"]:
        print("sandbox_stderr:")
        print((result["sandbox_stderr"] or result["error_traceback"]).rstrip())
    print(f"parse_success: {str(result['parse_success']).lower()}")
    if result["critic_result"]:
        print("critic_result:")
        for key, value in result["critic_result"].items():
            print(f"- {key}: {value}")
        print("fallback_validation_result:")
    else:
        print("validation_result:")
    _print_json(result["validation_result"])
    print(f"workflow_continued: {str(result['workflow_continued']).lower()}")


def main(
    *,
    sandbox_runner: SandboxRunner | None = None,
) -> list[dict[str, Any]]:
    print("=== E2B Error Handling Demo ===")
    if sandbox_runner is None:
        sandbox_runner = run_python_in_sandbox
    has_e2b_key = bool((os.getenv("E2B_API_KEY") or "").strip())
    use_real_e2b = has_e2b_key and real_e2b_available(sandbox_runner)
    if not has_e2b_key:
        print("E2B_API_KEY missing; using simulated sandbox result for demo.")
    elif not use_real_e2b:
        print(
            "Real E2B execution failed; falling back to simulated sandbox for demo."
        )

    results = [
        run_case(
            case_name,
            sandbox_runner=sandbox_runner,
            use_real_e2b=use_real_e2b,
        )
        for case_name in CASE_CODES
    ]
    for index, result in enumerate(results, start=1):
        print_case(result, index)

    print("\nDemo summary:")
    print("- valid_code_success: passed")
    print("- sandbox_execution_error: recovered")
    print("- invalid_json_stdout: recovered")
    print("- workflow_continued = True")
    return results


if __name__ == "__main__":
    main()
