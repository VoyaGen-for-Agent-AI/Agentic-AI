import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import manual_e2b_error_handling_demo as demo


def test_valid_code_success_parses_passed_result():
    result = demo.run_case("valid_code_success", use_real_e2b=False)

    assert result["execution_status"] == "success"
    assert result["parse_success"] is True
    assert result["validation_result"]["validation_status"] == "passed"
    assert result["workflow_continued"] is True


def test_sandbox_execution_error_returns_fallback():
    result = demo.run_case("sandbox_execution_error", use_real_e2b=False)

    assert result["execution_status"] == "error"
    assert result["parse_success"] is False
    assert result["critic_result"]["error_type"] == "runtime_error"
    assert result["validation_result"]["validation_status"] == "failed"
    assert result["validation_result"]["source"] == "e2b_error_fallback"
    assert result["workflow_continued"] is True


def test_invalid_json_stdout_is_classified():
    result = demo.run_case("invalid_json_stdout", use_real_e2b=False)

    assert result["execution_status"] == "success"
    assert result["parse_success"] is False
    assert result["critic_result"]["error_type"] == "invalid_json"
    assert result["validation_result"]["validation_status"] == "warning"
    assert result["workflow_continued"] is True


def test_missing_e2b_key_does_not_crash(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    results = demo.main()

    assert len(results) == 3
    assert all(result["sandbox_source"] == "simulated_e2b" for result in results)
    assert all(result["workflow_continued"] is True for result in results)


def test_main_output_does_not_expose_api_key(monkeypatch, capsys):
    secret = "should-never-appear"
    monkeypatch.setenv("E2B_API_KEY", secret)
    def fake_runner(code):
        if "e2b-demo-ready" in code:
            return {
                "status": "success",
                "stdout": "e2b-demo-ready\n",
                "stderr": "",
                "error": None,
            }
        return demo._simulated_sandbox_result(
            "sandbox_execution_error"
            if "RuntimeError" in code
            else "invalid_json_stdout"
            if "{bad json" in code
            else "valid_code_success"
        )

    results = demo.main(sandbox_runner=fake_runner)
    output = capsys.readouterr().out

    assert len(results) == 3
    assert all(result["sandbox_source"] == "e2b_sandbox" for result in results)
    assert all(result["workflow_continued"] is True for result in results)
    assert secret not in output


def test_real_e2b_probe_failure_falls_back_to_simulation(
    monkeypatch, capsys
):
    monkeypatch.setenv("E2B_API_KEY", "fake-test-key")

    results = demo.main(
        sandbox_runner=lambda code: {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": "sandbox unavailable",
        }
    )
    output = capsys.readouterr().out

    assert (
        "Real E2B execution failed; falling back to simulated sandbox for demo."
        in output
    )
    assert all(result["sandbox_source"] == "simulated_e2b" for result in results)
    assert all(result["workflow_continued"] is True for result in results)


def test_sandbox_traceback_secrets_are_redacted(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "private-e2b-key")
    monkeypatch.setenv("TAVILY_API_KEY", "private-tavily-key")

    result = demo.run_case(
        "sandbox_execution_error",
        use_real_e2b=True,
        sandbox_runner=lambda code: {
            "status": "error",
            "stdout": "",
            "stderr": (
                "E2B=private-e2b-key TAVILY=private-tavily-key "
                "RuntimeError: demo"
            ),
            "error": "RuntimeError: demo",
        },
    )

    assert "private-e2b-key" not in result["sandbox_stderr"]
    assert "private-tavily-key" not in result["sandbox_stderr"]
    assert result["sandbox_stderr"].count("[REDACTED]") == 2
