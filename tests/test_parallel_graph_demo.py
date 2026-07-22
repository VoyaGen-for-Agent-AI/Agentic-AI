import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.manual_parallel_graph_demo import (
    DEMO_PROMPT,
    parallel_graph,
    run_benchmark,
    run_with_timeline,
    sequential_graph,
    verify_parallel_execution,
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


def test_timeline_contains_required_fields(monkeypatch):
    _disable_live_modes(monkeypatch)

    _, total_seconds, timeline = run_with_timeline(parallel_graph)

    assert isinstance(total_seconds, float)
    assert {item["node_name"] for item in timeline} == {"weather", "spot", "booking"}
    for item in timeline:
        assert {"node_name", "start_time", "end_time", "duration_seconds"} <= set(item)
        assert all(isinstance(item[key], float) for key in ("start_time", "end_time", "duration_seconds"))


def test_verify_parallel_execution_accepts_overlapping_simulated_timeline():
    sequential_timeline = [
        {"node_name": "weather", "start_time": 0.0, "end_time": 0.5, "duration_seconds": 0.5},
        {"node_name": "spot", "start_time": 0.5, "end_time": 1.0, "duration_seconds": 0.5},
        {"node_name": "booking", "start_time": 1.0, "end_time": 1.5, "duration_seconds": 0.5},
    ]
    parallel_timeline = [
        {"node_name": "weather", "start_time": 0.0, "end_time": 0.5, "duration_seconds": 0.5},
        {"node_name": "spot", "start_time": 0.01, "end_time": 0.51, "duration_seconds": 0.5},
        {"node_name": "booking", "start_time": 0.02, "end_time": 0.52, "duration_seconds": 0.5},
    ]

    verified, reason = verify_parallel_execution(sequential_timeline, parallel_timeline)

    assert verified is True
    assert isinstance(reason, str)
    assert reason
