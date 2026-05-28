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


def test_contract_check_accepts_configured_psql_bin(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    psql_bin = tmp_path / "psql.exe"
    psql_bin.write_text("fake psql\n", encoding="utf-8")
    monkeypatch.setattr(check_contracts.shutil, "which", lambda name: None)
    check_contracts.SUPABASE_DB_URL = "postgresql://direct.example/postgres"
    check_contracts.SUPABASE_POOLER_DB_URL = ""
    check_contracts.SUPABASE_ACCESS_TOKEN = ""
    check_contracts.PSQL_BIN = str(psql_bin)

    check_contracts.require_env()


def test_contract_check_uses_configured_psql_bin(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    psql_bin = tmp_path / "psql.exe"
    psql_bin.write_text("fake psql\n", encoding="utf-8")
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(args: list[str], **_kwargs: object) -> Completed:
        calls.append(args)
        return Completed()

    monkeypatch.setattr(check_contracts.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_contracts.subprocess, "run", fake_run)
    check_contracts.SUPABASE_DB_URL = "postgresql://direct.example/postgres"
    check_contracts.SUPABASE_POOLER_DB_URL = ""
    check_contracts.PSQL_BIN = str(psql_bin)

    assert check_contracts.run_sql("select 1") == ["ok"]
    assert calls[0][0] == str(psql_bin)


def test_contract_check_uses_docker_exec_when_psql_is_unavailable(
    check_contracts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(args: list[str], **_kwargs: object) -> Completed:
        calls.append(args)
        return Completed()

    monkeypatch.setattr(
        check_contracts.shutil,
        "which",
        lambda name: "docker.exe" if name == "docker" else None,
    )
    monkeypatch.setattr(check_contracts.subprocess, "run", fake_run)
    check_contracts.SUPABASE_DB_URL = ""
    check_contracts.SUPABASE_POOLER_DB_URL = ""
    check_contracts.PSQL_BIN = ""
    check_contracts.SUPABASE_DB_CONTAINER = "supabase_db_Parser"

    assert check_contracts.run_sql("select 1") == ["ok"]
    assert calls[0] == [
        "docker.exe",
        "exec",
        "supabase_db_Parser",
        "psql",
        "--username",
        "postgres",
        "--dbname",
        "postgres",
        "--no-align",
        "--tuples-only",
        "--quiet",
        "--command",
        "select 1",
    ]


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


def test_contract_expected_tables_includes_migration_046_047(check_contracts) -> None:
    assert "source_pack_import_runs" in check_contracts.EXPECTED_TABLES
    assert "context_build_runs" in check_contracts.EXPECTED_TABLES


def test_contract_rls_tables_includes_migration_046_047(check_contracts) -> None:
    assert "source_pack_import_runs" in check_contracts.RLS_TABLES
    assert "context_build_runs" in check_contracts.RLS_TABLES


def test_contract_api_only_tables_includes_migration_046_047(check_contracts) -> None:
    assert "source_pack_import_runs" in check_contracts.API_ONLY_TABLES
    assert "context_build_runs" in check_contracts.API_ONLY_TABLES


def test_contract_expected_indexes_includes_migration_046_047_048(check_contracts) -> None:
    assert "idx_source_pack_import_runs_workspace_id" in check_contracts.EXPECTED_INDEXES
    assert "idx_context_build_runs_workspace_created_at" in check_contracts.EXPECTED_INDEXES
    assert "idx_token_usage_job_id" in check_contracts.EXPECTED_INDEXES


def test_required_task010_scripts_exist() -> None:
    assert (ROOT / "scripts" / "smoke" / "real_readiness.py").exists()
    assert (ROOT / "scripts" / "smoke" / "run_real_smoke.py").exists()
    assert (ROOT / "scripts" / "smoke" / "check_supabase_contracts.py").exists()
    assert (ROOT / "scripts" / "smoke" / "supabase_smoke.py").exists()
    assert (ROOT / "scripts" / "smoke" / "diagnose_source.py").exists()
    assert (ROOT / "scripts" / "smoke" / "cleanup_smoke.py").exists()
    assert (ROOT / "scripts" / "ops" / "storage_gc.py").exists()
    assert not (ROOT / "scripts" / "dev" / "check_local_stack.ps1").exists()
    assert not (ROOT / "scripts" / "dev" / "start_local_stack.ps1").exists()
    assert not (ROOT / "scripts" / "dev" / "stop_local_stack.ps1").exists()
    assert not (ROOT / "scripts" / "dev" / "setup_redis_windows.ps1").exists()


def test_real_smoke_orchestrator_does_not_reference_dev_runtime_scripts() -> None:
    script = (ROOT / "scripts" / "smoke" / "run_real_smoke.py").read_text(
        encoding="utf-8"
    )

    assert "powershell_cmd" not in script
    assert "--start-stack" not in script
    assert "--no-start" not in script
    assert "--skip-stack-check" not in script
    assert "setup-redis" not in script
    assert "start-stack" not in script
    assert "stack-check" not in script
    assert "scripts/dev/" not in script.replace("\\", "/")


def test_docker_local_runtime_uses_root_compose_not_legacy_infra_layout() -> None:
    assert (ROOT / "compose.yaml").exists()
    assert (ROOT / "Dockerfile.python").exists()
    assert (ROOT / "Dockerfile.web").exists()
    assert (ROOT / ".dockerignore").exists()
    assert (ROOT / ".env.docker.example").exists()
    assert (ROOT / "docs" / "operations" / "DOCKER_LOCAL_RUNTIME.md").exists()
    assert (ROOT / "docs" / "operations" / "LOCAL_RUNTIME.md").exists()

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!.env.docker.example" in gitignore
    assert not (ROOT / "infra" / "docker-compose.yml").exists()
    assert not (ROOT / "infra" / "docker" / "Dockerfile.api").exists()
    assert not (ROOT / "infra" / "docker" / "Dockerfile.worker").exists()
