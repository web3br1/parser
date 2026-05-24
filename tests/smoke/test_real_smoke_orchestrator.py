from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "scripts" / "smoke" / "run_real_smoke.py"


def load_orchestrator() -> Any:
    module_name = "run_real_smoke_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ORCHESTRATOR,
    )
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


def command_text(command: object) -> str:
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command)


def phase_names(report_path: Path) -> list[str]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return [phase["name"] for phase in report["phases"]]


class FakeHealthResponse:
    status_code = 200
    text = '{"status":"ok"}'

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"status": "ok"}


@pytest.fixture()
def real_smoke() -> Any:
    return load_orchestrator()


@pytest.fixture()
def fake_health(real_smoke: Any, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    def fake_get(url: str, **_kwargs: object) -> FakeHealthResponse:
        urls.append(url)
        return FakeHealthResponse()

    monkeypatch.setattr(real_smoke.httpx, "get", fake_get)
    return urls


@pytest.fixture()
def fake_subprocess(real_smoke: Any, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append([str(part) for part in command])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="phase ok\n",
            stderr="",
        )

    monkeypatch.setattr(real_smoke.subprocess, "run", fake_run)
    return calls


def test_local_full_phase_order_validates_running_runtime_without_stack_check(
    real_smoke: Any,
    fake_subprocess: list[list[str]],
    fake_health: list[str],
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "local-full.json"

    code = run_cli(
        real_smoke,
        ["--target", "local", "--full", "--json-report", str(report_path)],
    )

    assert code == 0
    assert phase_names(report_path) == [
        "readiness",
        "contracts",
        "health",
        "smoke-min",
        "smoke-full",
    ]
    executed = [command_text(command) for command in fake_subprocess]
    assert "scripts/smoke/real_readiness.py" in executed[0].replace("\\", "/")
    assert "scripts/smoke/check_supabase_contracts.py" in executed[1].replace("\\", "/")
    assert "scripts/smoke/supabase_smoke.py" in executed[2].replace("\\", "/")
    assert "scripts/smoke/supabase_smoke.py" in executed[3].replace("\\", "/")
    assert "--full" in executed[3]
    assert all("scripts/dev/" not in command.replace("\\", "/") for command in executed)
    assert fake_health == ["http://localhost:8000/health"]


@pytest.mark.parametrize("legacy_flag", ["--start-stack", "--skip-stack-check", "--no-start"])
def test_legacy_stack_flags_are_rejected_as_unknown(
    real_smoke: Any,
    legacy_flag: str,
) -> None:
    assert run_cli(real_smoke, [legacy_flag]) == 2


def test_cloud_full_skips_local_stack_phases_and_uses_api_base_url(
    real_smoke: Any,
    fake_health: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "cloud-full.json"
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(([str(part) for part in command], dict(kwargs["env"])))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="phase ok\n",
            stderr="",
        )

    monkeypatch.setattr(real_smoke.subprocess, "run", fake_run)

    code = run_cli(
        real_smoke,
        [
            "--target",
            "cloud",
            "--full",
            "--api-base-url",
            "https://api.example.test",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 0
    assert phase_names(report_path) == [
        "readiness",
        "contracts",
        "health",
        "smoke-min",
        "smoke-full",
    ]
    executed = [command_text(command).replace("\\", "/") for command, _env in calls]
    assert all("scripts/dev/" not in command for command in executed)
    assert fake_health == ["https://api.example.test/health"]
    smoke_commands = [command for command in executed if "supabase_smoke.py" in command]
    assert smoke_commands
    smoke_envs = [env for command, env in calls if "supabase_smoke.py" in command_text(command)]
    assert smoke_envs
    assert all(env["API_BASE_URL"] == "https://api.example.test" for env in smoke_envs)


def test_cloud_requires_explicit_api_base_url_when_env_missing(
    real_smoke: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("API_BASE_URL", raising=False)
    report_path = tmp_path / "cloud-missing-api.json"

    code = run_cli(
        real_smoke,
        ["--target", "cloud", "--json-report", str(report_path)],
    )

    assert code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["phases"] == []


def test_skip_flags_remove_readiness_and_contracts(
    real_smoke: Any,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "skip-flags.json"

    code = run_cli(
        real_smoke,
        [
            "--target",
            "local",
            "--skip-readiness",
            "--skip-contracts",
            "--dry-run",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 0
    assert phase_names(report_path) == ["health", "smoke-min"]


def test_first_failure_stops_later_phases_by_default(
    real_smoke: Any,
    fake_health: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        text = command_text(command).replace("\\", "/")
        calls.append(text)
        returncode = 1 if "check_supabase_contracts.py" in text else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="failed contract\n" if returncode else "ok\n",
            stderr="",
        )

    monkeypatch.setattr(real_smoke.subprocess, "run", fake_run)
    report_path = tmp_path / "stop-on-failure.json"

    code = run_cli(
        real_smoke,
        ["--target", "local", "--full", "--json-report", str(report_path)],
    )

    assert code == 1
    assert phase_names(report_path) == ["readiness", "contracts"]
    assert len(calls) == 2
    assert fake_health == []


def test_continue_on_failure_records_later_safe_phases(
    real_smoke: Any,
    fake_health: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        text = command_text(command).replace("\\", "/")
        calls.append(text)
        returncode = 1 if "check_supabase_contracts.py" in text else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="failed contract\n" if returncode else "ok\n",
            stderr="",
        )

    monkeypatch.setattr(real_smoke.subprocess, "run", fake_run)
    report_path = tmp_path / "continue-on-failure.json"

    code = run_cli(
        real_smoke,
        [
            "--target",
            "local",
            "--full",
            "--continue-on-failure",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 1
    assert phase_names(report_path) == [
        "readiness",
        "contracts",
        "health",
        "smoke-min",
        "smoke-full",
    ]
    assert len(calls) == 4
    assert all("scripts/dev/" not in command for command in calls)
    assert fake_health == ["http://localhost:8000/health"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["phases"][1]["status"] == "failed"
    assert report["phases"][-1]["status"] == "passed"


def test_dry_run_records_planned_phases_without_execution(
    real_smoke: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not execute subprocesses")

    def fail_get(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not execute health checks")

    monkeypatch.setattr(real_smoke.subprocess, "run", fail_run)
    monkeypatch.setattr(real_smoke.httpx, "get", fail_get)
    report_path = tmp_path / "dry-run.json"

    code = run_cli(
        real_smoke,
        [
            "--target",
            "cloud",
            "--full",
            "--api-base-url",
            "https://api.example.test",
            "--dry-run",
            "--json-report",
            str(report_path),
        ],
    )

    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "planned"
    assert phase_names(report_path) == [
        "readiness",
        "contracts",
        "health",
        "smoke-min",
        "smoke-full",
    ]
    assert all(phase["status"] == "planned" for phase in report["phases"])
    planned_commands = [command_text(phase["command"]).replace("\\", "/") for phase in report["phases"]]
    assert all("scripts/dev/" not in command for command in planned_commands)


def test_json_report_redacts_sentinel_secrets(
    real_smoke: Any,
    fake_health: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_url = "test-postgres-url-with-password"
    secret_key = "test-service-role-key-value"
    report_path = tmp_path / "redacted-report.json"

    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_key)
    monkeypatch.setenv("SUPABASE_DB_URL", secret_url)

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"stdout has {secret_key}\n",
            stderr=f"stderr has {secret_url}\n",
        )

    monkeypatch.setattr(real_smoke.subprocess, "run", fake_run)

    code = run_cli(
        real_smoke,
        ["--target", "local", "--json-report", str(report_path)],
    )

    assert code == 0
    assert fake_health == ["http://localhost:8000/health"]
    report_text = report_path.read_text(encoding="utf-8")
    assert secret_key not in report_text
    assert secret_url not in report_text
    assert "test-service-role-key-value" not in report_text
    assert "test-postgres-url-with-password" not in report_text
    assert "[REDACTED]" in report_text
