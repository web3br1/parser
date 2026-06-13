from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SCHEMA_VERSION = "parser_quality_gate.v1"
DEFAULT_DIRTY_CORPUS = Path(".run/industrial-real")
NEXT_ACTION_CATEGORIES = [
    "write_red_test",
    "fix_parser",
    "update_baseline_with_reason",
    "inspect_dirty_corpus",
    "ready_for_next_slice",
]


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...], *, cwd: Path) -> CommandResult:
        ...


@dataclass(frozen=True)
class LayerSpec:
    name: str
    required: bool
    commands: tuple[tuple[str, ...], ...]
    failure_next_action: str


class SubprocessCommandRunner:
    def run(self, command: tuple[str, ...], *, cwd: Path) -> CommandResult:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    dirty_corpus_dir = _resolve_repo_path(repo_root, args.dirty_corpus_dir)

    report = build_quality_gate_report(
        repo_root=repo_root,
        dirty_corpus_dir=dirty_corpus_dir,
    )

    rendered = render_report_json(report)
    if args.report:
        report_path = _resolve_repo_path(repo_root, args.report)
        assert report_path is not None
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the layered Parser quality gate and emit a JSON report.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dirty-corpus-dir", type=Path, default=DEFAULT_DIRTY_CORPUS)
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def build_quality_gate_report(
    *,
    repo_root: Path,
    dirty_corpus_dir: Path | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    runner = command_runner or SubprocessCommandRunner()
    dirty_dir = dirty_corpus_dir or repo_root / DEFAULT_DIRTY_CORPUS
    layers = [
        _run_layer(
            spec,
            repo_root=repo_root,
            command_runner=runner,
            dirty_corpus_dir=dirty_dir,
        )
        for spec in _layer_specs(repo_root=repo_root, dirty_corpus_dir=dirty_dir)
    ]
    required_failed_layers = [
        str(layer["name"])
        for layer in layers
        if layer["required"] is True and layer["result"] == "fail"
    ]
    status = "fail" if required_failed_layers else "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "next_action": _gate_next_action(layers, status=status),
        "next_action_categories": NEXT_ACTION_CATEGORIES,
        "required_failed_layers": required_failed_layers,
        "layers": layers,
    }


def render_report_json(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _layer_specs(*, repo_root: Path, dirty_corpus_dir: Path) -> list[LayerSpec]:
    dirty_output = dirty_corpus_dir / "benchmark-latest.json"
    return [
        LayerSpec(
            name="catalog",
            required=True,
            commands=(_uv("pytest", "tests\\smoke\\test_parser_fragility_catalog.py", "-q"),),
            failure_next_action="write_red_test",
        ),
        LayerSpec(
            name="fixtures",
            required=True,
            commands=(_uv("pytest", "tests\\smoke\\test_parser_fragility_fixtures.py", "-q"),),
            failure_next_action="write_red_test",
        ),
        LayerSpec(
            name="negative_adversarial",
            required=True,
            commands=(
                _uv(
                    "pytest",
                    "packages\\parsers\\tests\\test_industrial_negative_adversarial.py",
                    "-q",
                ),
            ),
            failure_next_action="fix_parser",
        ),
        LayerSpec(
            name="invariants",
            required=True,
            commands=(
                _uv(
                    "pytest",
                    "packages\\parsers\\tests\\test_industrial_invariants.py",
                    "-q",
                ),
            ),
            failure_next_action="fix_parser",
        ),
        LayerSpec(
            name="ground_truth_eval",
            required=True,
            commands=(_uv("python", "scripts\\quality\\parser_ground_truth_eval.py"),),
            failure_next_action="fix_parser",
        ),
        LayerSpec(
            name="regression_ratchet",
            required=True,
            commands=(
                _uv(
                    "python",
                    "scripts\\quality\\parser_regression_ratchet.py",
                    "--dirty-corpus-dir",
                    _display_path(repo_root=repo_root, path=dirty_corpus_dir),
                ),
            ),
            failure_next_action="update_baseline_with_reason",
        ),
        LayerSpec(
            name="dirty_benchmark_optional",
            required=False,
            commands=(
                _uv(
                    "python",
                    "scripts\\industrial\\benchmark_dirty_documents.py",
                    "--input-dir",
                    _display_path(repo_root=repo_root, path=dirty_corpus_dir),
                    "--output",
                    _display_path(repo_root=repo_root, path=dirty_output),
                ),
            ),
            failure_next_action="inspect_dirty_corpus",
        ),
        LayerSpec(
            name="lint_type_secret",
            required=True,
            commands=(
                _uv("ruff", "check", "packages\\parsers", "scripts", "tests"),
                _uv("mypy", "--ignore-missing-imports", "-p", "parsers"),
                _uv("python", "scripts\\ci\\secret_scan.py"),
            ),
            failure_next_action="fix_parser",
        ),
    ]


def _run_layer(
    spec: LayerSpec,
    *,
    repo_root: Path,
    command_runner: CommandRunner,
    dirty_corpus_dir: Path,
) -> dict[str, object]:
    command_display = " && ".join(_display_command(command) for command in spec.commands)
    if spec.name == "dirty_benchmark_optional" and not dirty_corpus_dir.exists():
        return {
            "name": spec.name,
            "required": spec.required,
            "result": "skip",
            "command": command_display,
            "exit_codes": [],
            "failure_summary": f"{_display_path(repo_root=repo_root, path=dirty_corpus_dir)} not found",
            "next_action": "inspect_dirty_corpus",
        }

    results = [
        command_runner.run(command, cwd=repo_root)
        for command in spec.commands
    ]
    failures = [result for result in results if result.exit_code != 0]
    result = "fail" if failures else "pass"
    return {
        "name": spec.name,
        "required": spec.required,
        "result": result,
        "command": command_display,
        "exit_codes": [command_result.exit_code for command_result in results],
        "failure_summary": (
            _failure_summary(failures)
            if failures
            else None
        ),
        "next_action": (
            spec.failure_next_action
            if failures
            else "ready_for_next_slice"
        ),
    }


def _gate_next_action(layers: list[dict[str, object]], *, status: str) -> str:
    if status == "pass":
        return "ready_for_next_slice"
    for layer in layers:
        if layer["required"] is True and layer["result"] == "fail":
            return str(layer["next_action"])
    return "ready_for_next_slice"


def _failure_summary(failures: Sequence[CommandResult]) -> str:
    parts: list[str] = []
    for failure in failures:
        message = (failure.stderr or failure.stdout).strip()
        if not message:
            message = f"exit code {failure.exit_code}"
        parts.append(_single_line(message))
    return " | ".join(parts)


def _single_line(value: str) -> str:
    return " ".join(value.split())[:600]


def _uv(*args: str) -> tuple[str, ...]:
    return ("uv", "run", "--cache-dir", ".uv-cache", *args)


def _display_command(command: Sequence[str]) -> str:
    return " ".join(command)


def _display_path(*, repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _resolve_repo_path(repo_root: Path, value: Path | None) -> Path | None:
    if value is None:
        return value
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


if __name__ == "__main__":
    raise SystemExit(main())
