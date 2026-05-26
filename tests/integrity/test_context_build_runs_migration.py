from __future__ import annotations

from pathlib import Path

MIGRATION = Path("supabase/migrations/047_context_build_runs.sql")
MIGRATIONS = Path("supabase/migrations")


def test_context_build_runs_is_next_migration() -> None:
    assert (MIGRATIONS / "046_source_pack_import_runs.sql").exists()
    assert MIGRATION.exists()


def test_context_build_runs_table_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "create table public.context_build_runs" in sql
    assert "workspace_id uuid not null references public.workspaces(id) on delete cascade" in sql
    assert "actor_user_id uuid references auth.users(id) on delete set null" in sql
    assert "input_fingerprint text not null" in sql
    assert "input_hash text" in sql
    assert "input_hash text not null" not in sql

    for value in ("single_document", "multi_document_batch", "source_pack"):
        assert f"'{value}'" in sql

    for value in (
        "created",
        "preflighted",
        "queued",
        "processing",
        "needs_review",
        "ready_to_export",
        "compiled",
        "rejected",
        "failed",
    ):
        assert f"'{value}'" in sql

    for value in ("normal_ingest", "batch_ingest", "compile_as_source_pack", "reject"):
        assert f"'{value}'" in sql


def test_context_build_runs_payload_and_bundle_fields() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for column in (
        "source_dir text",
        "source_pack_id text",
        "source_pack_version text",
        "staged_upload_id text",
        "source_count integer not null default 0 check (source_count >= 0)",
        "job_count integer not null default 0 check (job_count >= 0)",
        "bundle_hash text",
        "context_version text",
        "output_path text",
        "readiness_status text check",
        "readiness_score integer check",
        "file_counts jsonb not null default '{}'::jsonb",
        "missing_files jsonb not null default '[]'::jsonb",
        "extra_files jsonb not null default '[]'::jsonb",
        "steps jsonb not null default '[]'::jsonb",
        "warnings jsonb not null default '[]'::jsonb",
        "errors jsonb not null default '[]'::jsonb",
        "metadata jsonb not null default '{}'::jsonb",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz not null default now()",
    ):
        assert column in sql

    for value in ("ready", "warning", "blocked"):
        assert f"'{value}'" in sql


def test_context_build_runs_rls_trigger_and_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "alter table public.context_build_runs enable row level security" in sql
    assert "create trigger trg_context_build_runs_updated_at" in sql
    assert "before update on public.context_build_runs" in sql
    assert "for each row execute function public.touch_updated_at()" in sql

    for index_name in (
        "idx_context_build_runs_workspace_created_at",
        "idx_context_build_runs_workspace_status",
        "idx_context_build_runs_workspace_input_mode",
        "idx_context_build_runs_workspace_input_fingerprint",
        "idx_context_build_runs_workspace_input_hash",
        "idx_context_build_runs_source_pack",
    ):
        assert index_name in sql


def test_context_build_runs_is_backend_owned() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "revoke all on public.context_build_runs from anon, authenticated" in sql
    assert "grant all on public.context_build_runs to service_role" in sql
    assert "create policy" not in sql
