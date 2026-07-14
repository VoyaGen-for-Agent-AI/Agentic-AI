import json
import os
import re
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from prompts.itinerary_prompt import ITINERARY_SYSTEM_PROMPT


def _extract_json(content: str) -> str:
    markdown_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if markdown_match:
        return markdown_match.group(1).strip()
    return content.strip()


def _last_user_request(state: AgentState) -> str:
    if state.get("user_query"):
        return str(state["user_query"])
    if state.get("messages"):
        return str(state["messages"][0].content)
    return "請規劃台中兩天一夜行程。"


def _trip_context(state: AgentState) -> str:
    fields = {
        "origin": state.get("origin"),
        "departure_station": state.get("departure_station"),
        "destination": state.get("destination"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "days": state.get("days"),
        "nights": state.get("nights"),
        "preference": state.get("preference"),
        "total_budget": state.get("total_budget"),
    }
    return "\n".join(f"{key}: {value}" for key, value in fields.items() if value not in (None, "", []))


def itinerary_node(state: AgentState) -> dict[str, Any]:
    print("🗺️  [Itinerary Agent] 正在產生 AI 行程規劃...")

    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.3-70b-instruct:free",
        api_key=os.getenv("OPENAI_API_KEY"),  # type: ignore
    )

    messages = [
        SystemMessage(content=ITINERARY_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"使用者需求：{_last_user_request(state)}\n\n"
                f"已解析旅遊欄位：\n{_trip_context(state)}"
            )
        ),
    ]

    try:
        response = llm.invoke(messages)
        parsed = json.loads(_extract_json(str(response.content)))
    except (JSONDecodeError, TypeError, ValueError):
        return {
            "execution_status": "error",
            "error_traceback": "Invalid itinerary JSON",
            "current_task": "travel",
            "next_step": "FINISH",
        }
    except Exception as exc:
        return {
            "execution_status": "error",
            "error_traceback": str(exc),
            "current_task": "travel",
            "next_step": "FINISH",
        }

    return {
        "itinerary_result": parsed,
        "travel_result": parsed,
        "current_task": "travel",
        "next_step": "final_response",
    }


def travel_node(state: AgentState) -> dict[str, Any]:
    return itinerary_node(state)
