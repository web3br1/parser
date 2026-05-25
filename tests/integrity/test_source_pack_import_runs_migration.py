from __future__ import annotations

from pathlib import Path

MIGRATION = Path("supabase/migrations/046_source_pack_import_runs.sql")


def test_source_pack_import_runs_migration_exists() -> None:
    assert MIGRATION.exists()


def test_source_pack_import_runs_table_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "create table public.source_pack_import_runs" in sql
    assert "workspace_id uuid not null references public.workspaces(id)" in sql
    assert "actor_user_id uuid references auth.users(id)" in sql
    assert "source_pack_id text" in sql
    assert "source_pack_version text" in sql
    assert "source_dir text" in sql
    assert "input_hash text not null" in sql
    assert "bundle_hash text" in sql
    assert "context_version text" in sql
    assert "output_path text" in sql
    assert "readiness_status text" in sql
    assert "manifest_document_count integer not null default 0" in sql
    assert "official_reference_count integer not null default 0" in sql
    assert "missing_files jsonb not null default '[]'::jsonb" in sql
    assert "extra_files jsonb not null default '[]'::jsonb" in sql
    assert "errors jsonb not null default '[]'::jsonb" in sql


def test_source_pack_import_runs_rls_and_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "alter table public.source_pack_import_runs enable row level security" in sql
    assert "idx_source_pack_import_runs_workspace_id" in sql
    assert "idx_source_pack_import_runs_input_hash" in sql
    assert "idx_source_pack_import_runs_pack" in sql
    assert "idx_source_pack_import_runs_status" in sql


def test_source_pack_import_runs_is_backend_owned() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "revoke all on public.source_pack_import_runs from anon, authenticated" in sql
    assert "grant all on public.source_pack_import_runs to service_role" in sql
    assert "create policy" not in sql
