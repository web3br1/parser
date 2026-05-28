import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"


def _all_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8").lower() for path in sorted(MIGRATIONS.glob("*.sql"))
    )


def _grant_execute_statements_for_role(role: str) -> list[tuple[str, str]]:
    statements: list[tuple[str, str]] = []
    role_pattern = re.compile(rf"\bto\s+{re.escape(role)}\b", re.IGNORECASE)

    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql_without_comments = "\n".join(
            line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
        )
        for statement in sql_without_comments.split(";"):
            normalized = " ".join(statement.split()).lower()
            if normalized.startswith("grant execute") and role_pattern.search(normalized):
                statements.append((path.name, normalized))

    return statements


def test_integrity_migrations_exist() -> None:
    expected = {
        "029_integrity_constraints.sql",
        "030_ingest_rpc.sql",
        "031_classification_rpc.sql",
        "032_extraction_rpc.sql",
        "033_security_definer_grants.sql",
    }

    assert expected.issubset({path.name for path in MIGRATIONS.glob("*.sql")})


def test_source_file_hash_unique_index_exists() -> None:
    sql = (MIGRATIONS / "029_integrity_constraints.sql").read_text(encoding="utf-8")

    assert "uq_sources_workspace_file_hash_active" in sql
    assert "workspace_id, file_hash" in sql
    assert "where deleted_at is null" in sql


def test_atomic_rpc_contracts_exist() -> None:
    combined = "\n".join(
        [
            (MIGRATIONS / "030_ingest_rpc.sql").read_text(encoding="utf-8"),
            (MIGRATIONS / "031_classification_rpc.sql").read_text(encoding="utf-8"),
            (MIGRATIONS / "032_extraction_rpc.sql").read_text(encoding="utf-8"),
        ]
    )

    assert "complete_ingest_job" in combined
    assert "complete_classification_job" in combined
    assert "complete_extraction_job" in combined


def test_service_role_rpc_contracts_accept_explicit_actor() -> None:
    workspace_sql = (MIGRATIONS / "025_workspace_schema_policies.sql").read_text(
        encoding="utf-8"
    )
    review_sql = (MIGRATIONS / "028_review_functions.sql").read_text(encoding="utf-8")

    assert "actor_user_id uuid" in workspace_sql
    assert "p_actor_user_id uuid" in review_sql
    assert "has_workspace_role_for_user" in review_sql


def test_publish_functions_are_restricted_to_owner_manager() -> None:
    sql = (MIGRATIONS / "044_restrict_publish_to_managers.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "create or replace function public.publish_fact" in sql
    assert "create or replace function public.publish_rule" in sql
    assert "array['owner','manager']::workspace_role[]" in sql
    assert "array['owner','manager','reviewer']::workspace_role[]" not in sql


def test_unknown_reclassification_job_has_idempotency_key() -> None:
    sql = (MIGRATIONS / "028_review_functions.sql").read_text(encoding="utf-8")

    assert "idempotency_key" in sql
    assert "digest(" in sql
    assert "extraction:manual:" in sql


def test_api_required_job_rpc_exists() -> None:
    sql = (MIGRATIONS / "029_integrity_constraints.sql").read_text(encoding="utf-8")

    assert "get_or_create_processing_job" in sql
    assert "on conflict (idempotency_key)" in sql


def test_storage_contract_matches_api_paths() -> None:
    sql = (MIGRATIONS / "024_storage_policies.sql").read_text(encoding="utf-8").lower()
    lock_down_sql = (MIGRATIONS / "040_lock_down_storage_read_policy.sql").read_text(
        encoding="utf-8"
    ).lower()
    storage_write_lock_down_sql = (
        MIGRATIONS / "043_lock_down_storage_client_writes.sql"
    ).read_text(encoding="utf-8").lower()
    storage_size_sql = (MIGRATIONS / "042_storage_file_size_100mb.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "context-builder-private" in sql
    assert "workspaces" in sql
    assert "sources" in sql
    assert "104857600" in sql
    assert "104857600" in storage_size_sql
    assert "for select" not in sql
    assert 'drop policy if exists "members can read private workspace files"' in lock_down_sql
    for policy_name in {
        "managers can upload private workspace files",
        "managers can update private workspace files",
        "owners can delete private workspace files",
    }:
        assert f'drop policy if exists "{policy_name}"' in storage_write_lock_down_sql
    assert "storage writes must go through the api/service role" in storage_write_lock_down_sql


def test_privacy_requests_migration_contract_exists() -> None:
    migration = MIGRATIONS / "038_privacy_requests.sql"
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table public.privacy_requests" in sql
    for column in {
        "id uuid primary key",
        "workspace_id uuid not null references public.workspaces",
        "request_type text not null",
        "status text not null",
        "requested_by uuid references auth.users",
        "dry_run_plan jsonb not null",
        "confirmation_required boolean not null",
        "metadata jsonb not null",
        "created_at timestamptz not null",
        "updated_at timestamptz not null",
    }:
        assert column in sql

    assert "alter table public.privacy_requests enable row level security" in sql
    assert "has_workspace_role(workspace_id, array['owner']::workspace_role[])" in sql
    assert "for select" in sql
    assert "for insert" not in sql
    assert "idx_privacy_requests_workspace_id" in sql
    assert "idx_privacy_requests_workspace_status" in sql


def test_published_views_are_security_invoker() -> None:
    sql = (MIGRATIONS / "014_published_views.sql").read_text(encoding="utf-8")

    assert sql.count("security_invoker = true") >= 3


def test_published_fact_and_rule_views_require_published_active_sources() -> None:
    sql = (MIGRATIONS / "014_published_views.sql").read_text(encoding="utf-8").lower()

    published_facts_sql = sql.split("create view public.published_rules", 1)[0]
    published_rules_sql = sql.split("create view public.published_rules", 1)[1].split(
        "create view public.published_sources", 1
    )[0]

    for view_sql, table_alias in (
        (published_facts_sql, "f"),
        (published_rules_sql, "r"),
    ):
        assert "join public.sources s" in view_sql
        assert f"s.id = {table_alias}.source_id" in view_sql
        assert f"s.workspace_id = {table_alias}.workspace_id" in view_sql
        assert "s.status = 'published'" in view_sql
        assert "s.deleted_at is null" in view_sql


def test_source_status_contract_includes_extracted_in_sql_and_domain() -> None:
    sql = _all_sql()
    states_py = (ROOT / "packages" / "domain" / "src" / "domain" / "states.py").read_text(
        encoding="utf-8"
    )
    source_state_body = states_py.split("class SourceState", 1)[1].split(
        "class ChunkState", 1
    )[0]

    assert "add value if not exists 'extracted'" in sql
    assert 'EXTRACTED = "extracted"' in source_state_body


def test_source_state_finalizer_blocks_publish_on_pending_review_inputs() -> None:
    sql = (MIGRATIONS / "037_job_claim_and_source_state.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "from public.chunks" in sql
    assert "status = 'needs_review'" in sql
    assert "from public.unknown_facts_queue" in sql
    assert "status in ('open', 'schema_requested')" in sql
    assert "from public.contradictions" in sql
    assert "status in ('open', 'needs_review')" in sql


def test_source_state_backfill_invokes_finalizer_for_existing_non_terminal_sources() -> None:
    migration = MIGRATIONS / "045_backfill_source_state.sql"
    sql = migration.read_text(encoding="utf-8").lower()

    assert "finalize_source_state_after_extraction(id, workspace_id)" in sql
    assert "from public.sources" in sql
    assert "status in ('processing', 'extracted', 'needs_review')" in sql


def test_security_definer_functions_have_grants() -> None:
    sql = (MIGRATIONS / "033_security_definer_grants.sql").read_text(encoding="utf-8")

    # RLS helpers must be callable by authenticated for policy evaluation.
    assert "is_workspace_member" in sql
    assert "has_workspace_role" in sql
    assert "to authenticated" in sql

    # Worker RPCs must NOT appear in any GRANT ... TO authenticated statement.
    # (They may appear in comments — so check actual grant lines.)
    grant_lines = [
        line.strip().lower()
        for line in sql.splitlines()
        if line.strip().lower().startswith("grant") and "to authenticated" in line.lower()
    ]
    worker_rpcs = {"complete_ingest_job", "complete_classification_job", "complete_extraction_job"}
    for line in grant_lines:
        for rpc in worker_rpcs:
            assert rpc not in line, f"Worker RPC {rpc!r} must not be granted to authenticated"

    # service_role gets full access via schema-level grant.
    assert "grant execute on all functions in schema public to service_role" in sql


def test_security_definer_rpc_execution_is_revoked_from_public_roles() -> None:
    sql = _all_sql()

    assert "revoke execute on all functions in schema public from public" in sql
    assert "revoke execute on all functions in schema public from anon" in sql
    assert "revoke execute on all functions in schema public from authenticated" in sql


def test_worker_rpcs_are_never_granted_to_authenticated() -> None:
    grant_statements = _grant_execute_statements_for_role("authenticated")
    worker_rpcs = {
        "complete_ingest_job",
        "complete_classification_job",
        "complete_extraction_job",
        "get_or_create_processing_job",
    }

    for migration_name, statement in grant_statements:
        assert "all functions in schema public" not in statement, (
            f"{migration_name} grants every public function to authenticated"
        )
        for rpc in worker_rpcs:
            assert rpc not in statement, (
                f"{migration_name} grants worker RPC {rpc!r} to authenticated"
            )


def test_sensitive_review_tables_are_api_only_for_public_roles() -> None:
    sql = (MIGRATIONS / "020_rls.sql").read_text(encoding="utf-8").lower()
    sensitive_tables = {
        "business_rules",
        "chunks",
        "evidence_spans",
        "extracted_facts",
        "unknown_facts_queue",
        "contradictions",
    }

    assert "frontend access model: api-only" in sql

    for table in sensitive_tables:
        assert f"revoke all on table public.{table} from anon" in sql
        assert f"revoke all on table public.{table} from authenticated" in sql
        assert f"grant all on table public.{table} to service_role" in sql

        table_policy_sql = re.findall(
            rf"create policy\s+\"[^\"]+\"\s+on public\.{table}\s+for select\b.*?;",
            sql,
            flags=re.DOTALL,
        )
        assert table_policy_sql == [], (
            f"public.{table} must not have direct SELECT policies for client roles"
        )


def test_client_roles_cannot_write_workspace_source_tables_directly() -> None:
    sql = _all_sql()
    lock_down_sql = (MIGRATIONS / "041_lock_down_client_writes.sql").read_text(
        encoding="utf-8"
    ).lower()

    for policy_name in {
        "owners can update workspaces",
        "owners can manage workspace members",
        "managers can create sources",
        "managers can update sources",
    }:
        assert f'drop policy if exists "{policy_name}"' in lock_down_sql

    for table in {"workspaces", "workspace_members", "sources"}:
        assert f"revoke insert, update, delete on table public.{table} from anon" in sql
        assert f"revoke insert, update, delete on table public.{table} from authenticated" in sql
        assert f"grant all on table public.{table} to service_role" in sql


def test_seed_contains_all_seven_mvp_fact_types() -> None:
    sql = (MIGRATIONS / "021_seed_mvp_schemas.sql").read_text(encoding="utf-8")

    for fact_type in {
        "service_price",
        "business_hours",
        "payment_method",
        "discount_rule",
        "cancellation_policy",
        "contact_info",
        "faq_item",
    }:
        assert f"'{fact_type}'" in sql


def test_token_usage_log_supports_worker_payload_contract() -> None:
    creation_sql = (MIGRATIONS / "017_token_usage.sql").read_text(encoding="utf-8").lower()
    worker_contract_sql = (MIGRATIONS / "048_token_usage_worker_contract.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "estimated_cost numeric" in creation_sql
    assert "add column if not exists job_id uuid references public.processing_jobs" in (
        worker_contract_sql
    )
    assert "add column if not exists prompt_version text" in worker_contract_sql
    assert "idx_token_usage_job_id" in worker_contract_sql
