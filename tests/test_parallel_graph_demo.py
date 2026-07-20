import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.manual_parallel_graph_demo import (
    DEMO_PROMPT,
    parallel_graph,
    run_benchmark,
    sequential_graph,
)


def _disable_live_modes(monkeypatch):
    for name in ("USE_LIVE_WEATHER", "USE_LIVE_TRAFFIC", "USE_LIVE_ITINERARY"):
        monkeypatch.setenv(name, "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_DEMO_DELAY_SECONDS", raising=False)


def test_sequential_graph_can_complete_without_api_key(monkeypatch):
    _disable_live_modes(monkeypatch)

    result = sequential_graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    assert result["final_answer"]
    assert result["budget_result"]["source"] == "rule_based"


def test_parallel_graph_can_complete_and_join_results_without_api_key(monkeypatch):
    _disable_live_modes(monkeypatch)

    result = parallel_graph.invoke({"messages": [HumanMessage(content=DEMO_PROMPT)]})

    assert result["final_answer"]
    assert result["weather_result"]
    assert result["spot_result"]
    assert result["booking_result"]
    assert result["weather_result"]["source"] == "mock_fallback"
    assert result["traffic_result"]["source"] == "mock_fallback"
    assert result["itinerary_result"]["source"] == "mock_fallback"


def test_benchmark_summary_contains_numeric_statistics(monkeypatch):
    _disable_live_modes(monkeypatch)

    summary = run_benchmark(runs=2, warmup=0)

    expected_fields = {
        "sequential_avg_seconds",
        "parallel_avg_seconds",
        "sequential_median_seconds",
        "parallel_median_seconds",
        "sequential_min_seconds",
        "parallel_min_seconds",
        "sequential_max_seconds",
        "parallel_max_seconds",
        "median_saved_seconds",
        "median_latency_reduction_percent",
        "avg_latency_reduction_percent",
    }
    assert set(summary) == expected_fields
    assert all(isinstance(value, float) for value in summary.values())
