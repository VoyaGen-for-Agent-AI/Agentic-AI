import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.manual_main_graph_demo import get_user_query


def test_get_user_query_returns_default_query_for_empty_input(monkeypatch):
    default_query = "預設台中兩天一夜行程"
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    assert get_user_query(default_query) == default_query


def test_get_user_query_returns_custom_query(monkeypatch):
    custom_query = "請安排台南三天兩夜美食行程"
    monkeypatch.setattr("builtins.input", lambda prompt: custom_query)

    assert get_user_query("預設行程") == custom_query
