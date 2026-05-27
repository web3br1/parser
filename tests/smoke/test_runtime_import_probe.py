from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "smoke" / "runtime_import_probe.py"


def load_probe() -> Any:
    module_name = "runtime_import_probe_under_test"
    spec = importlib.util.spec_from_file_location(module_name, PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(module: Any, argv: list[str]) -> int:
    try:
        result = module.main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(result or 0)


@pytest.fixture()
def probe() -> Any:
    return load_probe()


def read_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_command_fails_and_writes_report(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND", raising=False)
    report_path = tmp_path / "runtime-import.json"

    code = run_cli(probe, ["--json-report", str(report_path)])

    assert code == 2
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["error"] == "runtime_import_command_required"
    assert report["command"] == []
    assert report["returncode"] is None


def test_successful_command_writes_sanitized_report_and_expands_bundle(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_key = "test-service-role-key-value"
    bundle_path = tmp_path / "bundle.context_bundle.v1.json"
    report_path = tmp_path / "runtime-import.json"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_key)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"imported {command[-1]} with {secret_key}\n",
            stderr=f"clean stderr {secret_key}\n",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        [
            "--bundle-path",
            str(bundle_path),
            "--command",
            f'"{sys.executable}" -m runtime_probe --bundle {{bundle}}',
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 0
    assert calls == [
        (
            [sys.executable, "-m", "runtime_probe", "--bundle", str(bundle_path)],
            {
                "capture_output": True,
                "text": True,
                "check": False,
                "shell": False,
                "timeout": 900.0,
            },
        )
    ]
    report_text = report_path.read_text(encoding="utf-8")
    assert secret_key not in report_text
    report = json.loads(report_text)
    assert report["status"] == "passed"
    assert report["bundle_path"] == str(bundle_path)
    assert report["command"] == [sys.executable, "-m", "runtime_probe", "--bundle", str(bundle_path)]
    assert report["returncode"] == 0
    assert "[REDACTED]" in report["stdout_tail"]
    assert "[REDACTED]" in report["stderr_tail"]
    assert report["error"] is None


def test_unquoted_bundle_placeholder_preserves_windows_path_with_spaces(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Meus projetos" / "bundle.context_bundle.v1.json"
    report_path = tmp_path / "runtime-import.json"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        [
            "--bundle-path",
            str(bundle_path),
            "--command",
            f'"{sys.executable}" -m runtime_probe --bundle {{bundle}}',
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 0
    assert calls == [[sys.executable, "-m", "runtime_probe", "--bundle", str(bundle_path)]]


def test_failed_command_returns_1_and_records_returncode(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "runtime-import.json"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 17, stdout="nope\n", stderr="bad import\n")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        ["--command", f"{sys.executable} -m runtime_probe", "--json-report", str(report_path)],
    )

    assert code == 1
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["returncode"] == 17
    assert report["stderr_tail"] == "bad import\n"
    assert report["error"] is None


def test_missing_executable_returns_1_and_writes_report(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "runtime-import.json"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        ["--command", "missing-runtime-importer --bundle {bundle}", "--json-report", str(report_path)],
    )

    assert code == 1
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["returncode"] is None
    assert report["stdout_tail"] == ""
    assert report["stderr_tail"] == ""
    assert report["command"][0] == "missing-runtime-importer"
    assert report["error"] == "runtime_import_command_not_found"


def test_malformed_quote_command_returns_2_and_writes_invalid_error(
    probe: Any,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "runtime-import.json"

    code = run_cli(
        probe,
        ["--command", '"unterminated command', "--json-report", str(report_path)],
    )

    assert code == 2
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["error"] == "runtime_import_command_invalid"
    assert report["command"] == []
    assert report["returncode"] is None


def test_whitespace_command_returns_2_and_writes_invalid_error(
    probe: Any,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "runtime-import.json"

    code = run_cli(
        probe,
        ["--command", " \t  ", "--json-report", str(report_path)],
    )

    assert code == 2
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["error"] == "runtime_import_command_invalid"
    assert report["command"] == []
    assert report["returncode"] is None


def test_timeout_returns_1_and_records_timeout_error(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "runtime-import.json"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=1.5, output="partial out", stderr="partial err")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        [
            "--command",
            f"{sys.executable} -m runtime_probe",
            "--timeout-seconds",
            "1.5",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 1
    report = read_report(report_path)
    assert report["status"] == "failed"
    assert report["returncode"] is None
    assert report["stdout_tail"] == "partial out"
    assert report["stderr_tail"] == "partial err"
    assert report["error"] == "Timed out after 1.5s"


def test_timeout_with_bytes_stdout_stderr_redacts_report(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_key = "test-timeout-service-role-key-value"
    report_path = tmp_path / "runtime-import.json"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_key)

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            command,
            timeout=2.0,
            output=f"stdout {secret_key}".encode(),
            stderr=f"stderr {secret_key}".encode(),
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        [
            "--command",
            f"{sys.executable} -m runtime_probe",
            "--timeout-seconds",
            "2",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 1
    report_text = report_path.read_text(encoding="utf-8")
    assert secret_key not in report_text
    report = json.loads(report_text)
    assert report["status"] == "failed"
    assert report["stdout_tail"] == "stdout [REDACTED]"
    assert report["stderr_tail"] == "stderr [REDACTED]"
    assert report["error"] == "Timed out after 2s"


def test_command_from_env_works(
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "runtime-import.json"
    monkeypatch.setenv("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND", f'"{sys.executable}" -c pass {{bundle}}')
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        ["--bundle-path", str(bundle_path), "--json-report", str(report_path)],
    )

    assert code == 0
    assert calls == [[sys.executable, "-c", "pass", str(bundle_path)]]
    assert read_report(report_path)["status"] == "passed"
