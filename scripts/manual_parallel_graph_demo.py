import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.final_response import final_response_node
from agents.workers.booking_worker import booking_node
from agents.workers.budget_worker import budget_node
from agents.workers.spot_worker import spot_node
from agents.workers.traffic_worker import traffic_node
from agents.workers.travel_worker import travel_node
from agents.workers.trip_parser_worker import trip_parser_node
from agents.workers.weather_worker import weather_node
from core.state import AgentState


DEMO_PROMPT = (
    "我想在 7/18 到 7/19 從台北車站出發去台中兩天一夜，"
    "一人總預算 6000 元，希望行程不要太趕，想安排戶外景點，"
    "也請幫我找交通方便的住宿，最後估算整趟旅程的總花費。"
)

SOURCE_KEYS = (
    "weather_result",
    "spot_result",
    "booking_result",
    "traffic_result",
    "itinerary_result",
    "budget_result",
)


def _result_only_node(
    worker: Callable[[AgentState], dict[str, Any]], result_key: str
) -> Callable[[AgentState], dict[str, Any]]:
    """Prevent parallel branches from writing shared control-state keys."""
    def node(state: AgentState) -> dict[str, Any]:
        delay = _demo_delay_seconds()
        if delay:
            time.sleep(delay)
        update = worker(state)
        result = update.get(result_key, {})
        return {result_key: result}

    return node


def _demo_delay_seconds() -> float:
    raw_value = os.getenv("PARALLEL_DEMO_DELAY_SECONDS", "").strip()
    if not raw_value:
        return 0.0
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 0.0


weather_result_node = _result_only_node(weather_node, "weather_result")
spot_result_node = _result_only_node(spot_node, "spot_result")
booking_result_node = _result_only_node(booking_node, "booking_result")


def join_results_node(state: AgentState) -> dict[str, Any]:
    """Confirm all independent branch results exist before traffic planning."""
    missing = [
        key
        for key in ("weather_result", "spot_result", "booking_result")
        if not isinstance(state.get(key), dict) or not state.get(key)
    ]
    if missing:
        raise ValueError(f"Parallel result join missing: {', '.join(missing)}")
    return {"current_task": "join_results", "next_step": "traffic"}


def build_sequential_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("trip_parser", trip_parser_node)
    workflow.add_node("weather", weather_result_node)
    workflow.add_node("spot", spot_result_node)
    workflow.add_node("booking", booking_result_node)
    workflow.add_node("traffic", traffic_node)
    workflow.add_node("travel", travel_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("final_response", final_response_node)

    workflow.set_entry_point("trip_parser")
    workflow.add_edge("trip_parser", "weather")
    workflow.add_edge("weather", "spot")
    workflow.add_edge("spot", "booking")
    workflow.add_edge("booking", "traffic")
    workflow.add_edge("traffic", "travel")
    workflow.add_edge("travel", "budget")
    workflow.add_edge("budget", "final_response")
    workflow.add_edge("final_response", END)
    return workflow.compile()


def build_parallel_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("trip_parser", trip_parser_node)
    workflow.add_node("weather", weather_result_node)
    workflow.add_node("spot", spot_result_node)
    workflow.add_node("booking", booking_result_node)
    workflow.add_node("join_results", join_results_node)
    workflow.add_node("traffic", traffic_node)
    workflow.add_node("travel", travel_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("final_response", final_response_node)

    workflow.set_entry_point("trip_parser")
    workflow.add_edge("trip_parser", "weather")
    workflow.add_edge("trip_parser", "spot")
    workflow.add_edge("trip_parser", "booking")
    workflow.add_edge(["weather", "spot", "booking"], "join_results")
    workflow.add_edge("join_results", "traffic")
    workflow.add_edge("traffic", "travel")
    workflow.add_edge("travel", "budget")
    workflow.add_edge("budget", "final_response")
    workflow.add_edge("final_response", END)
    return workflow.compile()


sequential_graph = build_sequential_graph()
parallel_graph = build_parallel_graph()


def invoke_timed(graph, prompt: str = DEMO_PROMPT) -> tuple[dict[str, Any], float]:
    started_at = time.perf_counter()
    result = graph.invoke({"messages": [HumanMessage(content=prompt)]})
    return result, time.perf_counter() - started_at


def run_benchmark(runs: int = 10, warmup: int = 2) -> dict[str, float]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if warmup < 0:
        raise ValueError("warmup must be non-negative")

    for _ in range(warmup):
        invoke_timed(sequential_graph, DEMO_PROMPT)
        invoke_timed(parallel_graph, DEMO_PROMPT)

    sequential_times: list[float] = []
    parallel_times: list[float] = []
    for _ in range(runs):
        _, sequential_time = invoke_timed(sequential_graph, DEMO_PROMPT)
        _, parallel_time = invoke_timed(parallel_graph, DEMO_PROMPT)
        sequential_times.append(sequential_time)
        parallel_times.append(parallel_time)

    sequential_avg = statistics.mean(sequential_times)
    parallel_avg = statistics.mean(parallel_times)
    sequential_median = statistics.median(sequential_times)
    parallel_median = statistics.median(parallel_times)
    median_saved = sequential_median - parallel_median

    return {
        "sequential_avg_seconds": sequential_avg,
        "parallel_avg_seconds": parallel_avg,
        "sequential_median_seconds": sequential_median,
        "parallel_median_seconds": parallel_median,
        "sequential_min_seconds": min(sequential_times),
        "parallel_min_seconds": min(parallel_times),
        "sequential_max_seconds": max(sequential_times),
        "parallel_max_seconds": max(parallel_times),
        "median_saved_seconds": median_saved,
        "median_latency_reduction_percent": (
            median_saved / sequential_median * 100 if sequential_median else 0.0
        ),
        "avg_latency_reduction_percent": (
            (sequential_avg - parallel_avg) / sequential_avg * 100
            if sequential_avg
            else 0.0
        ),
    }


def _print_sources(label: str, state: dict[str, Any]) -> None:
    print(f"{label}_sources:")
    for key in SOURCE_KEYS:
        result = state.get(key, {})
        source = result.get("source", "missing") if isinstance(result, dict) else "missing"
        print(f"  {key}.source: {source}")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    for variable, label in (
        ("USE_LIVE_WEATHER", "Weather"),
        ("USE_LIVE_TRAFFIC", "Traffic"),
        ("USE_LIVE_ITINERARY", "Itinerary"),
    ):
        if os.getenv(variable, "").strip().lower() in {"1", "true", "yes", "on"}:
            print(f"{label} live mode enabled")

    sequential_state, sequential_time = invoke_timed(sequential_graph)
    parallel_state, parallel_time = invoke_timed(parallel_graph)
    saved_time = sequential_time - parallel_time
    reduction = (saved_time / sequential_time * 100) if sequential_time else 0.0

    print(f"sequential_time_seconds: {sequential_time:.6f}")
    print(f"parallel_time_seconds: {parallel_time:.6f}")
    print(f"saved_time_seconds: {saved_time:.6f}")
    print(f"latency_reduction_percent: {reduction:.2f}")
    _print_sources("sequential", sequential_state)
    _print_sources("parallel", parallel_state)
    print("parallel_final_answer:")
    print(parallel_state.get("final_answer", ""))

    print("benchmark_summary:")
    benchmark_summary = run_benchmark()
    for key, value in benchmark_summary.items():
        decimals = 2 if key.endswith("percent") else 6
        print(f"{key}: {value:.{decimals}f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
