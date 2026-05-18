from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any


def get_queued_jobs_for_reenqueue(*, older_than_minutes: int = 5) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    result = (
        _client()
        .table("processing_jobs")
        .select("*")
        .eq("status", "queued")
        .is_("started_at", "null")
        .lt("created_at", cutoff.isoformat())
        .in_("job_type", ["ingest", "classification", "extraction"])
        .execute()
    )
    return list(result.data or [])


def get_source_paths() -> set[str]:
    result = (
        _client()
        .table("sources")
        .select("storage_path")
        .not_.is_("storage_path", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    return {str(row["storage_path"]) for row in (result.data or [])}


def get_deleted_source_paths(*, older_than_hours: int = 0) -> set[str]:
    cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
    result = (
        _client()
        .table("sources")
        .select("storage_path")
        .not_.is_("storage_path", "null")
        .not_.is_("deleted_at", "null")
        .lt("deleted_at", cutoff.isoformat())
        .execute()
    )
    return {str(row["storage_path"]) for row in (result.data or [])}


def list_storage_objects(prefix: str) -> list[dict[str, Any]]:
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    result = _client().storage.from_(bucket).list(prefix)
    return list(result or [])


def delete_storage_objects(paths: list[str]) -> None:
    if not paths:
        return
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    _client().storage.from_(bucket).remove(paths)


def count_sources_for_retention(workspace_id: str) -> int:
    result = (
        _client()
        .table("sources")
        .select("id")
        .eq("workspace_id", workspace_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return len(result.data or [])


def count_storage_objects_for_retention(workspace_id: str) -> int:
    prefix = f"workspaces/{workspace_id}/sources"
    return len(list_storage_objects(prefix))


def count_audit_rows_for_anonymization(workspace_id: str) -> int:
    result = (
        _client()
        .table("audit_logs")
        .select("id")
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return len(result.data or [])


def _client() -> Any:
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
