import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.workers.travel_worker import itinerary_node


QUERY = "我想這週末從台北去台中兩天一夜，預算 6000 元，希望行程不要太趕，想安排戶外景點。"


def _has_api_key(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _configure_openrouter_key() -> bool:
    if _has_api_key("OPENAI_API_KEY"):
        return True

    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        os.environ["OPENAI_API_KEY"] = openrouter_key
        return True

    return False


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    if not _configure_openrouter_key():
        print("OPENROUTER_API_KEY or OPENAI_API_KEY is not set. Add one to .env to run this live itinerary test.")
        return

    state = {
        "messages": [HumanMessage(content=QUERY)],
        "user_query": QUERY,
        "route": "travel",
        "current_task": "",
        "next_step": "travel",
        "travel_result": {},
        "itinerary_result": {},
        "execution_status": "success",
        "error_traceback": "",
    }

    result = itinerary_node(state)  # type: ignore[arg-type]
    if result.get("execution_status") == "error":
        print(f"error_traceback: {result.get('error_traceback', '')}")
        return

    print("itinerary_result:")
    print(result.get("itinerary_result", {}))


if __name__ == "__main__":
    main()
