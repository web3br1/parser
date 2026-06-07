from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality" / "parser_quality_gate.py"


def load_gate() -> Any:
    module_name = "parser_quality_gate_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self, failures: dict[str, tuple[int, str]] | None = None) -> None:
        self.failures = failures or {}
        self.commands: list[str] = []

    def run(self, command: tuple[str, ...], *, cwd: Path) -> Any:
        display = " ".join(command)
        self.commands.append(display)
        for token, failure in self.failures.items():
            if token in display:
                exit_code, message = failure
                return load_gate().CommandResult(
                    command=command,
                    exit_code=exit_code,
                    stdout="",
                    stderr=message,
                )
        return load_gate().CommandResult(
            command=command,
            exit_code=0,
            stdout="ok",
            stderr="",
        )


def test_gate_report_has_ordered_layers_and_skips_missing_dirty_corpus(tmp_path: Path) -> None:
    gate = load_gate()
    runner = FakeRunner()

    report = gate.build_quality_gate_report(
        repo_root=ROOT,
        dirty_corpus_dir=tmp_path / "missing-dirty-corpus",
        command_runner=runner,
    )

    assert report["schema_version"] == "parser_quality_gate.v1"
    assert report["status"] == "pass"
    assert report["next_action"] == "ready_for_next_slice"
    assert "score" not in report
    assert [layer["name"] for layer in report["layers"]] == [
        "catalog",
        "fixtures",
        "negative_adversarial",
        "invariants",
        "regression_ratchet",
        "dirty_benchmark_optional",
        "lint_type_secret",
    ]
    dirty_layer = next(
        layer for layer in report["layers"] if layer["name"] == "dirty_benchmark_optional"
    )
    assert dirty_layer["result"] == "skip"
    assert dirty_layer["required"] is False
    assert dirty_layer["next_action"] == "inspect_dirty_corpus"
    assert dirty_layer["failure_summary"] == "missing-dirty-corpus not found"
    assert not any("benchmark_dirty_documents.py" in command for command in runner.commands)


def test_required_lower_layer_failure_fails_top_gate_with_actionable_summary(
    tmp_path: Path,
) -> None:
    gate = load_gate()
    runner = FakeRunner({
        "test_industrial_negative_adversarial.py": (
            1,
            "metadata promoted ambiguous appendix code",
        ),
    })

    report = gate.build_quality_gate_report(
        repo_root=ROOT,
        dirty_corpus_dir=tmp_path / "missing-dirty-corpus",
        command_runner=runner,
    )

    assert report["status"] == "fail"
    assert report["required_failed_layers"] == ["negative_adversarial"]
    failed_layer = next(
        layer for layer in report["layers"] if layer["name"] == "negative_adversarial"
    )
    assert failed_layer["result"] == "fail"
    assert failed_layer["next_action"] == "fix_parser"
    assert failed_layer["failure_summary"] == "metadata promoted ambiguous appendix code"


def test_regression_ratchet_failure_points_to_baseline_review_action(tmp_path: Path) -> None:
    gate = load_gate()
    runner = FakeRunner({
        "parser_regression_ratchet.py": (
            1,
            "signals.metadata_expected_hits dropped below baseline",
        ),
    })

    report = gate.build_quality_gate_report(
        repo_root=ROOT,
        dirty_corpus_dir=tmp_path / "missing-dirty-corpus",
        command_runner=runner,
    )

    failed_layer = next(
        layer for layer in report["layers"] if layer["name"] == "regression_ratchet"
    )
    assert report["status"] == "fail"
    assert failed_layer["result"] == "fail"
    assert failed_layer["next_action"] == "update_baseline_with_reason"
    assert failed_layer["failure_summary"] == (
        "signals.metadata_expected_hits dropped below baseline"
    )


def test_existing_dirty_corpus_runs_optional_benchmark_layer(tmp_path: Path) -> None:
    gate = load_gate()
    dirty_corpus = tmp_path / "industrial-real"
    dirty_corpus.mkdir()
    runner = FakeRunner()

    report = gate.build_quality_gate_report(
        repo_root=tmp_path,
        dirty_corpus_dir=dirty_corpus,
        command_runner=runner,
    )

    dirty_layer = next(
        layer for layer in report["layers"] if layer["name"] == "dirty_benchmark_optional"
    )
    assert dirty_layer["result"] == "pass"
    assert dirty_layer["command"].startswith(
        "uv run --cache-dir .uv-cache python scripts"
    )
    assert any("benchmark_dirty_documents.py" in command for command in runner.commands)


def test_report_json_is_deterministic_and_contains_all_next_actions(tmp_path: Path) -> None:
    gate = load_gate()
    report = gate.build_quality_gate_report(
        repo_root=ROOT,
        dirty_corpus_dir=tmp_path / "missing-dirty-corpus",
        command_runner=FakeRunner(),
    )

    rendered_once = gate.render_report_json(report)
    rendered_twice = gate.render_report_json(report)

    assert rendered_once == rendered_twice
    assert "generated_at" not in rendered_once
    payload = json.loads(rendered_once)
    assert payload["next_action_categories"] == [
        "write_red_test",
        "fix_parser",
        "update_baseline_with_reason",
        "inspect_dirty_corpus",
        "ready_for_next_slice",
    ]
