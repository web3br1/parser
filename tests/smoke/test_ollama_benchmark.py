from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeOllama:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return self.responses.pop(0)


def test_benchmark_case_records_ollama_usage_metrics() -> None:
    module = load_module(
        ROOT / "scripts" / "benchmark" / "ollama_benchmark.py",
        "ollama_benchmark_under_test",
    )
    client = FakeOllama([
        {
            "response": '{"classifications":[{"classification":"service_price"}]}',
            "total_duration": 2_000_000_000,
            "load_duration": 500_000_000,
            "prompt_eval_count": 100,
            "prompt_eval_duration": 1_000_000_000,
            "eval_count": 20,
            "eval_duration": 1_000_000_000,
        }
    ])

    result = module.run_benchmark_case(
        client,
        model="gemma4:31b",
        task_name="classification",
        prompt="Classifique em JSON",
        expected_contains="service_price",
        keep_alive="10m",
    )

    assert result["model"] == "gemma4:31b"
    assert result["task"] == "classification"
    assert result["parse_ok"] is True
    assert result["expected_ok"] is True
    assert result["total_seconds"] == 2.0
    assert result["load_seconds"] == 0.5
    assert result["prompt_tokens_per_second"] == 100.0
    assert result["output_tokens_per_second"] == 20.0
    assert client.calls[0]["format"] == "json"
    assert client.calls[0]["stream"] is False
    assert client.calls[0]["keep_alive"] == "10m"


def test_markdown_summary_orders_by_expected_then_total_time() -> None:
    module = load_module(
        ROOT / "scripts" / "benchmark" / "ollama_benchmark.py",
        "ollama_benchmark_markdown_under_test",
    )
    rows = [
        {
            "model": "slow",
            "task": "classification",
            "expected_ok": True,
            "parse_ok": True,
            "total_seconds": 10.0,
            "load_seconds": 1.0,
            "output_tokens_per_second": 5.0,
            "prompt_tokens": 1,
            "output_tokens": 1,
        },
        {
            "model": "fast",
            "task": "classification",
            "expected_ok": True,
            "parse_ok": True,
            "total_seconds": 2.0,
            "load_seconds": 0.0,
            "output_tokens_per_second": 20.0,
            "prompt_tokens": 1,
            "output_tokens": 1,
        },
    ]

    summary = module.render_markdown_summary(rows)

    assert summary.index("| fast |") < summary.index("| slow |")
    assert "tokens/s" in summary


def test_filter_cases_keeps_selected_tasks_only() -> None:
    module = load_module(
        ROOT / "scripts" / "benchmark" / "ollama_benchmark.py",
        "ollama_benchmark_filter_under_test",
    )

    cases = module.filter_cases(module.default_cases(), {"extraction"})

    assert cases
    assert {case["task"] for case in cases} == {"extraction"}
