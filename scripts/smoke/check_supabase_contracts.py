from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv_file(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
SUPABASE_POOLER_DB_URL = (
    os.getenv("SUPABASE_POOLER_DB_URL")
    or os.getenv("SUPABASE_IPV4_DB_URL")
    or os.getenv("DATABASE_POOLER_URL")
)
PSQL_BIN = os.getenv("PSQL_BIN") or os.getenv("SUPABASE_PSQL_BIN") or ""
SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN", "")
SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "")
# Local Docker Supabase fallback: docker exec <container> psql ...
# Set to the Postgres container name, e.g. supabase_db_Parser
SUPABASE_DB_CONTAINER = os.getenv("SUPABASE_DB_CONTAINER", "")
WORKSPACE_STORAGE_BUCKET = os.getenv("WORKSPACE_STORAGE_BUCKET", "context-builder-private")

EXPECTED_TABLES = [
    "workspaces",
    "workspace_members",
    "sources",
    "chunks",
    "extracted_facts",
    "business_rules",
    "unknown_facts_queue",
    "fact_type_schemas",
    "processing_jobs",
    "privacy_requests",
    # migrations 046-047: context build pipeline tracking
    "source_pack_import_runs",
    "context_build_runs",
]
RLS_TABLES = [
    "api_specs",
    "audit_logs",
    "business_rules",
    "chunks",
    "connector_instances",
    # migration 047
    "context_build_runs",
    "contradictions",
    "evidence_spans",
    "extracted_facts",
    "fact_type_schemas",
    "mcp_tool_calls",
    "mcp_tools",
    "privacy_requests",
    "processing_jobs",
    "query_audits",
    "source_quality_reports",
    # migration 046
    "source_pack_import_runs",
    "sources",
    "token_usage_log",
    "unknown_facts_queue",
    "validation_events",
    "workspace_members",
    "workspaces",
]
EXPECTED_RPCS = [
    "approve_fact",
    "approve_rule",
    "claim_processing_job",
    "complete_ingest_job",
    "complete_classification_job",
    "complete_extraction_job",
    "create_fact_version",
    "create_rule_version",
    "create_workspace_with_owner",
    "finalize_source_state_after_extraction",
    "get_or_create_processing_job",
    "ignore_unknown_item",
    "mark_fact_contradiction",
    "publish_fact",
    "publish_rule",
    "reclassify_unknown_item",
    "reject_fact",
    "reject_rule",
    "rollback_source_publication",
    "supersede_fact",
    "supersede_rule",
]
EXPECTED_EXTENSIONS = ["pgcrypto", "uuid-ossp"]
EXPECTED_INDEXES = [
    "uq_sources_workspace_file_hash_active",
    # migration 046: source_pack_import_runs
    "idx_source_pack_import_runs_workspace_id",
    # migration 047: context_build_runs
    "idx_context_build_runs_workspace_created_at",
    # migration 048: token_usage_log worker contract
    "idx_token_usage_job_id",
]
API_ONLY_TABLES = [
    "business_rules",
    "chunks",
    # migrations 046-047: backend-only (revoke all from anon, authenticated)
    "context_build_runs",
    "evidence_spans",
    "extracted_facts",
    "source_pack_import_runs",
    "unknown_facts_queue",
    "contradictions",
]
API_ONLY_WRITE_TABLES = [
    "sources",
    "workspace_members",
    "workspaces",
]
CRITICAL_RPC_SIGNATURES = [
    "public.approve_fact(uuid,jsonb,jsonb,text,uuid)",
    "public.approve_rule(uuid,jsonb,jsonb,text,uuid)",
    "public.claim_processing_job(uuid,text)",
    "public.complete_ingest_job(uuid,uuid,uuid,jsonb,jsonb)",
    "public.complete_classification_job(uuid,uuid,uuid,uuid,jsonb,text,jsonb,jsonb,text)",
    "public.complete_extraction_job(uuid,uuid,uuid,uuid,text,text,jsonb,jsonb,jsonb,jsonb)",
    "public.create_fact_version(uuid,jsonb,jsonb,text,uuid)",
    "public.create_rule_version(uuid,jsonb,jsonb,text,uuid)",
    "public.create_workspace_with_owner(text,text,jsonb,uuid)",
    "public.finalize_source_state_after_extraction(uuid,uuid)",
    "public.get_or_create_processing_job(uuid,uuid,uuid,text,text,jsonb)",
    "public.ignore_unknown_item(uuid,text,uuid)",
    "public.mark_fact_contradiction(uuid,uuid[],text,public.risk_level)",
    "public.publish_fact(uuid,text,uuid)",
    "public.publish_rule(uuid,text,uuid)",
    "public.reclassify_unknown_item(uuid,text,text,uuid,uuid,numeric,text,uuid)",
    "public.reject_fact(uuid,text,uuid)",
    "public.reject_rule(uuid,text,uuid)",
    "public.rollback_source_publication(uuid,text)",
    "public.supersede_fact(uuid,uuid,text)",
    "public.supersede_rule(uuid,uuid,text)",
]


def ok(message: str) -> None:
    print(f"OK   {message}")


def fail(message: str) -> None:
    print(f"FAIL {message}")
    sys.exit(1)


def require_env() -> None:
    missing = [
        name
        for name, value in {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        }.items()
        if not value
    ]
    can_run_sql_with_psql = bool(_database_urls() and _psql_command())
    can_run_sql_with_management_api = bool(SUPABASE_ACCESS_TOKEN and _project_ref())
    can_run_sql_with_docker_exec = _use_docker_exec()
    if not (can_run_sql_with_psql or can_run_sql_with_management_api or can_run_sql_with_docker_exec):
        missing.append(
            "SQL access: install psql or set PSQL_BIN/SUPABASE_PSQL_BIN and "
            "SUPABASE_DB_URL/DATABASE_URL (or SUPABASE_POOLER_DB_URL for IPv4/pooler), "
            "or set SUPABASE_ACCESS_TOKEN with SUPABASE_PROJECT_REF/project ref in "
            "SUPABASE_URL for Management API fallback, "
            "or set SUPABASE_DB_CONTAINER to the Postgres Docker container name "
            "(e.g. supabase_db_Parser) with docker available on PATH"
        )
    if missing:
        fail(f"Missing required env: {', '.join(missing)}")


def _project_ref() -> str:
    if SUPABASE_PROJECT_REF:
        return SUPABASE_PROJECT_REF
    hostname = urlparse(SUPABASE_URL).hostname or ""
    if hostname.endswith(".supabase.co"):
        return hostname.split(".", 1)[0]
    return ""


def _database_urls() -> list[str]:
    urls: list[str] = []
    for value in (SUPABASE_DB_URL, SUPABASE_POOLER_DB_URL):
        if value and value not in urls:
            urls.append(value)
    return urls


def _psql_command() -> str:
    if PSQL_BIN and Path(PSQL_BIN).exists():
        return PSQL_BIN
    return shutil.which("psql") or ""


def _docker_command() -> str:
    return shutil.which("docker") or ""


def _use_psql() -> bool:
    return bool(_database_urls() and _psql_command())


def _use_docker_exec() -> bool:
    return bool(SUPABASE_DB_CONTAINER and _docker_command())


def run_sql(sql: str) -> list[str]:
    if _use_psql():
        last_error = ""
        for database_url in _database_urls():
            completed = subprocess.run(
                [
                    _psql_command(),
                    database_url,
                    "--no-align",
                    "--tuples-only",
                    "--quiet",
                    "--command",
                    sql,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            last_error = completed.stderr.strip()
        fail(f"psql failed for all configured database URLs: {last_error}")

    if _use_docker_exec():
        completed = subprocess.run(
            [
                _docker_command(),
                "exec",
                SUPABASE_DB_CONTAINER,
                "psql",
                "--username",
                "postgres",
                "--dbname",
                "postgres",
                "--no-align",
                "--tuples-only",
                "--quiet",
                "--command",
                sql,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        fail(f"docker exec psql failed for container {SUPABASE_DB_CONTAINER!r}: {completed.stderr.strip()}")

    response = httpx.post(
        f"https://api.supabase.com/v1/projects/{_project_ref()}/database/query",
        headers={
            "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"query": sql},
        timeout=60.0,
    )
    if response.status_code not in {200, 201}:
        fail(f"Management API SQL failed: {response.status_code} {response.text}")
    rows = response.json()
    if not isinstance(rows, list):
        fail(f"Management API SQL returned unexpected payload: {response.text}")
    return [str(value) for row in rows for value in row.values() if value is not None]


def assert_sql_single_value(label: str, sql: str, expected: str) -> None:
    rows = run_sql(sql)
    if rows != [expected]:
        fail(f"{label} expected {expected}, got {rows}")
    ok(label)


def assert_sql_has_rows(label: str, sql: str, expected: set[str]) -> None:
    rows = set(run_sql(sql))
    missing = expected - rows
    if missing:
        fail(f"{label} missing: {', '.join(sorted(missing))}")
    ok(label)


def check_critical_rpc_privileges() -> None:
    values_sql = ", ".join(f"('{signature}')" for signature in CRITICAL_RPC_SIGNATURES)
    rows = run_sql(
        "select role_name || ':' || rpc_signature || ':' || can_execute "
        "from (values ('anon'), ('authenticated')) as roles(role_name) "
        f"cross join (values {values_sql}) as rpcs(rpc_signature) "
        "cross join lateral ("
        "  select has_function_privilege(role_name, rpc_signature, 'execute') as can_execute"
        ") privilege "
        "where can_execute = true;"
    )
    if rows:
        fail(f"Critical RPCs executable by public roles: {', '.join(rows)}")
    ok("critical worker RPCs are not executable by anon/authenticated")


def check_sensitive_table_privileges() -> None:
    values_sql = ", ".join(f"('{table_name}')" for table_name in API_ONLY_TABLES)
    rows = run_sql(
        "select role_name || ':' || table_name || ':' || privilege_name "
        "from (values ('anon'), ('authenticated')) as roles(role_name) "
        f"cross join (values {values_sql}) as tables(table_name) "
        "cross join (values ('select'), ('insert'), ('update'), ('delete')) as privileges(privilege_name) "
        "cross join lateral ("
        "  select has_table_privilege(role_name, 'public.' || table_name, privilege_name) as allowed"
        ") privilege "
        "where allowed = true;"
    )
    if rows:
        fail(f"Sensitive review tables exposed to public roles: {', '.join(rows)}")
    ok("sensitive review tables are API-only for anon/authenticated roles")


def check_client_write_privileges() -> None:
    values_sql = ", ".join(f"('{table_name}')" for table_name in API_ONLY_WRITE_TABLES)
    rows = run_sql(
        "select role_name || ':' || table_name || ':' || privilege_name "
        "from (values ('anon'), ('authenticated')) as roles(role_name) "
        f"cross join (values {values_sql}) as tables(table_name) "
        "cross join (values ('insert'), ('update'), ('delete')) as privileges(privilege_name) "
        "cross join lateral ("
        "  select has_table_privilege(role_name, 'public.' || table_name, privilege_name) as allowed"
        ") privilege "
        "where allowed = true;"
    )
    if rows:
        fail(f"Client roles can write API-owned tables directly: {', '.join(rows)}")
    ok("client roles cannot write workspace/source tables directly")


def check_bucket() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        fail("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    resp = httpx.get(
        f"{SUPABASE_URL}/storage/v1/bucket/{WORKSPACE_STORAGE_BUCKET}",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=30.0,
    )
    if resp.status_code != 200:
        fail(f"Bucket lookup failed: {resp.status_code} {resp.text}")
    data = resp.json()
    if data.get("public") is True:
        fail(f"Bucket {WORKSPACE_STORAGE_BUCKET} is public")
    file_size_limit = data.get("file_size_limit")
    if file_size_limit is not None and int(file_size_limit) < 104857600:
        fail(f"Bucket {WORKSPACE_STORAGE_BUCKET} file_size_limit is below 100 MB")
    ok(f"Private bucket exists: {WORKSPACE_STORAGE_BUCKET}")


def check_storage_read_policies() -> None:
    rows = run_sql(
        "select policyname "
        "from pg_policies "
        "where schemaname = 'storage' "
        "and tablename = 'objects' "
        "and cmd = 'SELECT' "
        "and qual ilike '%context-builder-private%';"
    )
    if rows:
        fail(f"Private storage bucket has direct SELECT policies: {', '.join(rows)}")
    ok("private storage has no direct client SELECT policy")


def check_storage_write_policies() -> None:
    rows = run_sql(
        "select policyname || ':' || cmd "
        "from pg_policies "
        "where schemaname = 'storage' "
        "and tablename = 'objects' "
        "and cmd in ('INSERT', 'UPDATE', 'DELETE') "
        "and (qual ilike '%context-builder-private%' or with_check ilike '%context-builder-private%');"
    )
    if rows:
        fail(f"Private storage bucket has direct client write policies: {', '.join(rows)}")
    ok("private storage has no direct client write policies")


def main() -> None:
    require_env()
    assert_sql_has_rows(
        "extensions installed",
        "select extname from pg_extension;",
        set(EXPECTED_EXTENSIONS),
    )
    assert_sql_has_rows(
        "tables exist",
        "select tablename from pg_tables where schemaname = 'public';",
        set(EXPECTED_TABLES),
    )
    assert_sql_has_rows(
        "RPCs exist",
        "select routine_name from information_schema.routines where routine_schema = 'public';",
        set(EXPECTED_RPCS),
    )
    assert_sql_has_rows(
        "indexes exist",
        "select indexname from pg_indexes where schemaname = 'public';",
        set(EXPECTED_INDEXES),
    )
    assert_sql_single_value(
        "unknown_facts_queue metadata column exists",
        (
            "select data_type from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'unknown_facts_queue' "
            "and column_name = 'metadata';"
        ),
        "jsonb",
    )
    # migration 047: context_build_runs key columns
    assert_sql_single_value(
        "context_build_runs.input_fingerprint column exists",
        (
            "select data_type from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'context_build_runs' "
            "and column_name = 'input_fingerprint';"
        ),
        "text",
    )
    assert_sql_single_value(
        "context_build_runs.input_mode column exists",
        (
            "select data_type from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'context_build_runs' "
            "and column_name = 'input_mode';"
        ),
        "text",
    )
    # migration 048: token_usage_log worker contract columns
    assert_sql_single_value(
        "token_usage_log.job_id column exists",
        (
            "select data_type from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'token_usage_log' "
            "and column_name = 'job_id';"
        ),
        "uuid",
    )
    assert_sql_single_value(
        "token_usage_log.prompt_version column exists",
        (
            "select data_type from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'token_usage_log' "
            "and column_name = 'prompt_version';"
        ),
        "text",
    )
    assert_sql_has_rows(
        "RLS enabled",
        (
            "select relname from pg_class "
            "where relnamespace = 'public'::regnamespace "
            "and relrowsecurity = true;"
        ),
        set(RLS_TABLES),
    )
    check_critical_rpc_privileges()
    check_sensitive_table_privileges()
    check_client_write_privileges()
    check_bucket()
    check_storage_read_policies()
    check_storage_write_policies()
    ok("Supabase contracts passed")


if __name__ == "__main__":
    main()
