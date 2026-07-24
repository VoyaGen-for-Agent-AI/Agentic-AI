"""Minimal E2B connectivity smoke test that automatically loads project .env."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.sandbox import run_python_in_sandbox

load_dotenv()


def _safe_text(value: Any) -> str:
    text = str(value or "")
    for name in (
        "E2B_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENWEATHER_API_KEY",
        "TAVILY_API_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_PUBLIC_KEY",
    ):
        secret = os.getenv(name) or ""
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def main() -> dict[str, Any]:
    print("=== E2B Smoke Test ===")
    result = run_python_in_sandbox('print("E2B sandbox is ready.")')
    safe_result = {
        "status": result.get("status"),
        "stdout": _safe_text(result.get("stdout")),
        "stderr": _safe_text(result.get("stderr")),
        "error": _safe_text(result.get("error")) or None,
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    return safe_result


if __name__ == "__main__":
    main()
