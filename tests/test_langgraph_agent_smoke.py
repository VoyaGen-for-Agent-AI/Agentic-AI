import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.trip_parser_worker import trip_parser_node
from core.state import AgentState


DEMO_PROMPT = (
    "我想這週末(7/18~7/19)從台北(台北車站出發)去台中兩天一夜，"
    "一人總預算 6000 元，希望行程不要太趕，想去戶外景點，也幫我找住宿"
)


def mock_weather_node(state: AgentState) -> dict:
    trip_request = state.get("trip_request", {})
    destination = trip_request.get("destination", "台中")
    return {
        "weather_result": {
            "destination": destination,
            "condition": "多雲時晴",
            "rain_probability": 30,
            "temperature": "26-32°C",
            "outdoor_risk": "low",
            "recommendation": "適合安排戶外景點，午後保留室內備案。",
        },
        "execution_status": "fallback",
        "next_step": "spot",
    }


def mock_spot_node(state: AgentState) -> dict:
    return {
        "spot_result": {
            "destination": "台中",
            "spots": [
                {
                    "name": "審計新村",
                    "type": "outdoor",
                    "estimated_stay_minutes": 90,
                    "ticket_cost": 0,
                    "reason": "符合戶外與輕鬆散步偏好。",
                },
                {
                    "name": "草悟道",
                    "type": "outdoor",
                    "estimated_stay_minutes": 80,
                    "ticket_cost": 0,
                    "reason": "市區步行友善，適合不要太趕的行程。",
                },
            ],
            "ticket_cost_total": 0,
            "recommendation": "以市區戶外景點為主，降低移動壓力。",
        },
        "execution_status": "fallback",
        "next_step": "booking",
    }


def mock_traffic_node(state: AgentState) -> dict:
    return {
        "traffic_result": {
            "segments": [
                {
                    "from": "台北車站",
                    "to": "台中車站",
                    "mode": "台鐵/高鐵",
                    "estimated_minutes": 90,
                    "estimated_cost": 700,
                    "note": "實際班次與票價以訂票系統為準。",
                }
            ],
            "route_points": ["台北車站", "台中車站", "審計新村", "草悟道"],
            "total_transport_time_minutes": 90,
            "total_transport_cost": 700,
            "feasibility": "good",
            "warning": "景點集中市區，交通負擔低。",
        },
        "execution_status": "fallback",
        "next_step": "travel",
    }


def mock_itinerary_node(state: AgentState) -> dict:
    itinerary_result = {
        "destination": "台中",
        "days": 2,
        "style": "relaxed",
        "schedule": [
            {
                "day": 1,
                "items": [
                    {
                        "time": "10:00",
                        "place": "台中車站",
                        "activity": "抵達與寄放行李",
                        "type": "transport",
                        "estimated_cost": 0,
                        "reason": "作為抵達點，方便後續市區移動。",
                    },
                    {
                        "time": "11:00",
                        "place": "審計新村",
                        "activity": "散步與逛文創小店",
                        "type": "outdoor",
                        "estimated_cost": 0,
                        "reason": "符合戶外與輕鬆行程偏好。",
                    },
                ],
            },
            {
                "day": 2,
                "items": [
                    {
                        "time": "10:00",
                        "place": "草悟道",
                        "activity": "散步與拍照",
                        "type": "outdoor",
                        "estimated_cost": 0,
                        "reason": "步行友善，適合第二天慢節奏安排。",
                    }
                ],
            },
        ],
        "ticket_cost_total": 0,
        "transport_hint": "以大眾運輸與步行為主。",
        "planning_reason": "景點集中市區，符合不要太趕的需求。",
    }
    return {
        "itinerary_result": itinerary_result,
        "travel_result": itinerary_result,
        "execution_status": "fallback",
        "next_step": "budget",
    }


def build_demo_safe_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("trip_parser", trip_parser_node)
    workflow.add_node("mock_weather", mock_weather_node)
    workflow.add_node("mock_spot", mock_spot_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("mock_traffic", mock_traffic_node)
    workflow.add_node("mock_itinerary", mock_itinerary_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("final_response", final_response_node)

    workflow.set_entry_point("trip_parser")
    workflow.add_edge("trip_parser", "mock_weather")
    workflow.add_edge("mock_weather", "mock_spot")
    workflow.add_edge("mock_spot", "booking")
    workflow.add_edge("booking", "mock_traffic")
    workflow.add_edge("mock_traffic", "mock_itinerary")
    workflow.add_edge("mock_itinerary", "budget")
    workflow.add_edge("budget", "final_response")
    workflow.add_edge("final_response", END)
    return workflow.compile()


def test_langgraph_agent_smoke_invokes_demo_safe_graph():
    graph = build_demo_safe_graph()

    result = graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    assert result["trip_request"]["destination"] == "台中"
    assert result["weather_result"]
    assert result["spot_result"]
    assert result["booking_result"]
    assert result["traffic_result"]
    assert result["itinerary_result"] or result["travel_result"]
    assert result["budget_result"]
    assert "台中" in result["final_answer"]
    assert "住宿" in result["final_answer"]
    assert "預算" in result["final_answer"]
