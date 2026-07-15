import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def test_normalize_route_from_plain_text():
    assert main.normalize_route("travel") == "travel"


def test_normalize_route_from_json_next():
    assert main.normalize_route('{"next": "travel"}') == "travel"


def test_normalize_route_from_json_route():
    assert main.normalize_route('{"route": "booking"}') == "booking"


def test_normalize_route_from_alias_itinerary():
    assert main.normalize_route("itinerary") == "travel"


def test_normalize_route_from_alias_hotel():
    assert main.normalize_route("hotel") == "booking"


def test_normalize_route_unknown_fallback():
    assert main.normalize_route("something random") == "travel"


def test_normalize_route_from_ai_message():
    assert main.normalize_route(AIMessage(content='{"route": "budget"}')) == "budget"


def test_supervisor_node_does_not_crash_on_plain_text_route(monkeypatch):
    class FakeSupervisorChain:
        def invoke(self, payload):
            assert payload["input"] == "請規劃台中兩天一夜"
            return "travel"

    monkeypatch.setattr(main, "supervisor_chain", FakeSupervisorChain())

    result = main.supervisor_node(
        {
            "messages": [HumanMessage(content="請規劃台中兩天一夜")],
        }
    )

    assert result["route"] == "travel"
    assert result["next_step"] == "travel"
    assert result["current_task"] == "supervisor"
