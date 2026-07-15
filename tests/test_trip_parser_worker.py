import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.trip_parser_worker import parse_trip_request, trip_parser_node


DEMO_QUERY = "我想這週末(7/18~7/19)從台北(台北車站出發)去台中兩天一夜，一人總預算 6000 元，希望行程不要太趕，想去戶外景點，也幫我找住宿"


def make_state(content=DEMO_QUERY, **overrides):
    state = {
        "messages": [HumanMessage(content=content)],
        "user_query": content,
        "route": "travel",
        "current_task": "",
        "next_step": "trip_parser",
        "weather_result": {},
        "movie_result": {},
        "travel_result": {},
        "booking_result": {},
        "budget_allocation": {},
        "budget_result": {},
        "transport_result": {},
        "itinerary_result": {},
        "scheduler_result": {},
        "safety_result": {},
        "traffic_result": {},
        "generated_code": "",
        "sandbox_stdout": "",
        "sandbox_stderr": "",
        "error_traceback": "",
        "critic_result": None,
        "execution_status": "success",
        "retry_count": 0,
        "final_answer": "",
    }
    state.update(overrides)
    return state


def apply_update(state, update):
    state.update(update)
    return state


def test_parse_demo_query():
    result = parse_trip_request(DEMO_QUERY)

    assert result["origin"] == "台北"
    assert result["departure_station"] == "台北車站"
    assert result["destination"] == "台中"
    assert result["start_date"] == "7/18"
    assert result["end_date"] == "7/19"
    assert result["days"] == 2
    assert result["nights"] == 1
    assert result["party_size"] == 1
    assert result["total_budget"] == 6000
    assert result["needs_booking"] is True
    assert result["needs_budget"] is True
    assert "不要太趕" in result["preference"] or "戶外景點" in result["preference"]


def test_parse_budget_variants():
    assert parse_trip_request("總預算 6000 元")["total_budget"] == 6000
    assert parse_trip_request("一人總預算 6000 元")["total_budget"] == 6000


def test_parse_days_nights_variants():
    assert parse_trip_request("兩天一夜")["days"] == 2
    assert parse_trip_request("兩天一夜")["nights"] == 1
    assert parse_trip_request("2天1夜")["days"] == 2
    assert parse_trip_request("2天1夜")["nights"] == 1


def test_trip_parser_node_updates_state():
    result = trip_parser_node(make_state())

    assert "trip_request" in result
    assert result["total_budget"] == 6000
    assert result["destination"] == "台中"
    assert result["next_step"] == "travel"


def test_trip_request_feeds_booking_and_budget():
    state = make_state()
    apply_update(state, trip_parser_node(state))
    state["itinerary_result"] = {"ticket_cost_total": 300}

    apply_update(state, booking_node(state))
    apply_update(state, budget_node(state))

    assert state["booking_result"]["recommended_hotel"]
    assert state["budget_result"]["breakdown"]["activity"] == 300
