from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def run_smoke(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(os.environ, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setitem(os.environ, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setitem(os.environ, "SUPABASE_SERVICE_ROLE_KEY", "service-role")
    return load_module(
        ROOT / "scripts" / "smoke" / "supabase_smoke.py",
        "supabase_smoke_under_test",
    )


@pytest.fixture()
def check_contracts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(os.environ, "SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setitem(os.environ, "SUPABASE_SERVICE_ROLE_KEY", "service-role")
    return load_module(
        ROOT / "scripts" / "smoke" / "check_supabase_contracts.py",
        "check_supabase_contracts_under_test",
    )


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = repr(payload)

    def json(self) -> object:
        return self._payload


class SequenceClient:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.paths: list[str] = []

    def get(self, path: str, **kwargs: object) -> FakeResponse:
        self.paths.append(path)
        return FakeResponse(200, self.payloads.pop(0))


def test_poll_ingest_waits_for_succeeded(run_smoke, monkeypatch: pytest.MonkeyPatch) -> None:
    client = SequenceClient(
        [
            {"status": "queued"},
            {"status": "processing"},
            {"status": "needs_review"},
            {"status": "succeeded"},
        ]
    )
    sleeps: list[int] = []
    monkeypatch.setattr(run_smoke.time, "sleep", lambda seconds: sleeps.append(seconds))

    run_smoke.step_poll_ingest(client, "workspace-id", "source-id")

    assert client.paths == [
        "/workspaces/workspace-id/sources/source-id/job",
        "/workspaces/workspace-id/sources/source-id/job",
        "/workspaces/workspace-id/sources/source-id/job",
        "/workspaces/workspace-id/sources/source-id/job",
    ]
    assert len(sleeps) == 3


def test_verify_chunks_allows_progressed_non_failed_statuses(
    run_smoke,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RestClient:
        def __enter__(self) -> RestClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, path: str, params: dict[str, str]) -> FakeResponse:
            return FakeResponse(
                200,
                [
                    {"id": "chunk-1", "status": "pending", "chunk_index": 0},
                    {"id": "chunk-2", "status": "classified", "chunk_index": 1},
                ],
            )

    monkeypatch.setattr(run_smoke, "supabase_rest", RestClient)

    chunk_ids = run_smoke.step_verify_chunks("workspace-id", "source-id")

    assert chunk_ids == ["chunk-1", "chunk-2"]


def test_verify_chunks_rejects_failed_status(run_smoke, monkeypatch: pytest.MonkeyPatch) -> None:
    class RestClient:
        def __enter__(self) -> RestClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, path: str, params: dict[str, str]) -> FakeResponse:
            return FakeResponse(
                200,
                [{"id": "chunk-1", "status": "failed", "chunk_index": 0}],
            )

    monkeypatch.setattr(run_smoke, "supabase_rest", RestClient)
    monkeypatch.setattr(
        run_smoke.sys,
        "exit",
        lambda code: (_ for _ in ()).throw(SystemExit(code)),
    )

    with pytest.raises(SystemExit):
        run_smoke.step_verify_chunks("workspace-id", "source-id")


def test_full_review_detail_uses_facts_field(run_smoke) -> None:
    class ReviewClient:
        def get(self, path: str, **kwargs: object) -> FakeResponse:
            return FakeResponse(
                200,
                {
                    "facts": [
                        {
                            "id": "fact-1",
                            "fact_type": "business_hours",
                        }
                    ],
                    "rules": [],
                },
            )

        def post(self, path: str, json: dict[str, object] | None = None) -> FakeResponse:
            return FakeResponse(200, {"status": "ok"})

    fact_id = run_smoke.step_approve_and_publish(ReviewClient(), "workspace-id", "chunk-id")

    assert fact_id == "fact-1"


def test_smoke_report_records_steps_and_writes_json(run_smoke, tmp_path: Path) -> None:
    report_path = tmp_path / "smoke-report.json"
    report = run_smoke.SmokeReport("FULL", "http://localhost:8000")

    report.ok("health", "API is up", workspace_id="workspace-id")
    report.write(report_path)

    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert '"status": "passed"' in text
    assert '"step": "health"' in text
    assert '"workspace_id": "workspace-id"' in text


def test_smoke_cli_supports_headless_flags(run_smoke) -> None:
    assert run_smoke.ARGS.no_color is False
    assert run_smoke.GREEN == ""
    assert run_smoke.RESET == ""


def test_contract_check_requires_actionable_sql_access(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_contracts.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_contracts.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    check_contracts.SUPABASE_DB_URL = "postgresql://direct.example/postgres"
    check_contracts.SUPABASE_POOLER_DB_URL = ""
    check_contracts.SUPABASE_ACCESS_TOKEN = ""

    with pytest.raises(SystemExit):
        check_contracts.require_env()


def test_contract_check_accepts_pooler_url_when_psql_exists(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_contracts.shutil, "which", lambda name: "psql")
    check_contracts.SUPABASE_DB_URL = ""
    check_contracts.SUPABASE_POOLER_DB_URL = "postgresql://pooler.example/postgres"
    check_contracts.SUPABASE_ACCESS_TOKEN = ""

    check_contracts.require_env()


def test_contract_check_rejects_client_write_privileges(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_contracts, "run_sql", lambda _sql: ["authenticated:sources:insert"])
    monkeypatch.setattr(
        check_contracts.sys,
        "exit",
        lambda code: (_ for _ in ()).throw(SystemExit(code)),
    )

    with pytest.raises(SystemExit):
        check_contracts.check_client_write_privileges()


def test_contract_check_rejects_private_storage_select_policy(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_contracts, "run_sql", lambda _sql: ["members can read"])
    monkeypatch.setattr(
        check_contracts.sys,
        "exit",
        lambda code: (_ for _ in ()).throw(SystemExit(code)),
    )

    with pytest.raises(SystemExit):
        check_contracts.check_storage_read_policies()


def test_source_diagnostic_report_counts_pipeline_rows() -> None:
    module = load_module(
        ROOT / "scripts" / "smoke" / "diagnose_source.py",
        "diagnose_source_under_test",
    )

    class RestClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str]]] = []

        def get(self, path: str, params: dict[str, str]) -> FakeResponse:
            self.calls.append((path, params))
            payloads = {
                "/sources": [{"id": "source-id", "status": "uploaded"}],
                "/processing_jobs": [{"id": "job-1", "status": "succeeded"}],
                "/chunks": [{"id": "chunk-1", "status": "extracted"}],
                "/extracted_facts": [
                    {"id": "fact-1", "status": "published", "fact_type": "service_price"}
                ],
                "/business_rules": [],
                "/unknown_facts_queue": [{"id": "unknown-1", "status": "open"}],
            }
            return FakeResponse(200, payloads[path])

    report = module.build_source_report(RestClient(), "workspace-id", "source-id")

    assert report["source"]["status"] == "uploaded"
    assert report["counts"]["jobs"] == 1
    assert report["counts"]["chunks"] == 1
    assert report["counts"]["facts"] == 1
    assert report["counts"]["unknowns"] == 1


def test_required_task010_scripts_exist() -> None:
    assert (ROOT / "scripts" / "smoke" / "check_supabase_contracts.py").exists()
    assert (ROOT / "scripts" / "smoke" / "supabase_smoke.py").exists()
    assert (ROOT / "scripts" / "dev" / "check_local_stack.ps1").exists()
    assert (ROOT / "scripts" / "dev" / "start_local_stack.ps1").exists()
    assert (ROOT / "scripts" / "dev" / "stop_local_stack.ps1").exists()
    assert (ROOT / "scripts" / "smoke" / "diagnose_source.py").exists()
    assert (ROOT / "scripts" / "smoke" / "cleanup_smoke.py").exists()
    assert (ROOT / "scripts" / "ops" / "storage_gc.py").exists()
    assert (ROOT / "scripts" / "dev" / "setup_redis_windows.ps1").exists()


def test_setup_redis_windows_uses_portable_redis_without_service_install() -> None:
    script = (ROOT / "scripts" / "dev" / "setup_redis_windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "tporadowski/redis" in script
    assert "REDIS_VERSION" in script
    assert "Invoke-WebRequest" in script
    assert "Expand-Archive" in script
    assert "redis-server.exe" in script
    assert ".run\\redis" in script
    assert "REDIS_URL=redis://localhost:$Port/0" in script
    assert "New-Service" not in script
    assert "sc.exe" not in script


def test_start_local_stack_defaults_to_real_workers() -> None:
    script = (ROOT / "scripts" / "dev" / "start_local_stack.ps1").read_text(
        encoding="utf-8"
    )
    assert "[int] $Port = 8000" in script
    assert "[switch] $Reload" in script
    assert "[switch] $Eager" in script
    assert "[switch] $FilesystemBroker" in script
    assert 'Set-ProcessEnv "CELERY_TASK_ALWAYS_EAGER" "0"' in script
    assert "CELERY_BROKER_URL" in script
    assert "filesystem://" in script
    assert "function Normalize-ProcessPathEnv" in script
    assert "UV_CACHE_DIR" in script
    assert 'Set-ProcessEnv "API_BASE_URL" "http://localhost:$Port"' in script
    assert '"--port", "$Port"' in script
    assert '"-Q", "ingest"' in script
    assert '"-Q", "classification"' in script
    assert '"-Q", "extraction"' in script
    assert '"--hostname", "parser-worker-ingest@%h"' in script
    assert '"--hostname", "parser-worker-classification@%h"' in script
    assert '"--hostname", "parser-worker-extraction@%h"' in script
    assert 'if ($Reload) {' in script
    assert '"--reload"' in script
    assert '"--reload"' not in script.split('if ($Reload) {', 1)[0]


def test_start_local_stack_cleans_stale_managed_processes_before_starting() -> None:
    script = (ROOT / "scripts" / "dev" / "start_local_stack.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Stop-StaleManagedProcess" in script
    assert "Get-CimInstance Win32_Process" in script
    assert "CommandLine" in script
    assert "worker_ingest.celery_app:app" in script
    assert "worker_classification.celery_app:app" in script
    assert "worker_extraction.celery_app:app" in script
    assert "Stop-StaleManagedProcess $Name $Arguments" in script
    assert script.index("Stop-StaleManagedProcess $Name $Arguments") < script.index(
        "$Process = Start-Process"
    )


def test_stop_local_stack_cleans_pidless_managed_processes() -> None:
    script = (ROOT / "scripts" / "dev" / "stop_local_stack.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Stop-ManagedProcessByCommand" in script
    assert "Get-CimInstance Win32_Process" in script
    assert "worker_ingest.celery_app:app" in script
    assert "worker_classification.celery_app:app" in script
    assert "worker_extraction.celery_app:app" in script
    assert "context_builder.main:app" in script


def test_dev_scripts_resolve_uv_from_env_or_common_windows_path() -> None:
    for path in [
        ROOT / "scripts" / "dev" / "check_local_stack.ps1",
        ROOT / "scripts" / "dev" / "start_local_stack.ps1",
    ]:
        script = path.read_text(encoding="utf-8")
        assert "function Resolve-UvPath" in script
        assert "UV_BIN" in script
        assert "miniforge3\\Scripts\\uv.exe" in script


def test_check_local_stack_detects_duplicate_workers() -> None:
    script = (ROOT / "scripts" / "dev" / "check_local_stack.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Count-ManagedProcesses" in script
    assert "worker_ingest.celery_app:app" in script
    assert "worker_classification.celery_app:app" in script
    assert "worker_extraction.celery_app:app" in script
    assert 'Write-Check "duplicate $($Spec.Name)"' in script
    assert "Duplicate worker processes detected" in script


def test_docker_is_not_a_project_runtime_contract() -> None:
    assert not (ROOT / "infra" / "docker-compose.yml").exists()
    assert not (ROOT / "infra" / "docker" / "Dockerfile.api").exists()
    assert not (ROOT / "infra" / "docker" / "Dockerfile.worker").exists()
