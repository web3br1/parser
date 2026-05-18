from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from supabase import Client

DELETE_CONFIRMATION_PHRASE = "DELETE_WORKSPACE_METADATA"


def build_privacy_plan(db: Client, workspace_id: str) -> dict[str, Any]:
    sources = _workspace_rows(db, "sources", workspace_id)
    active_sources = [source for source in sources if not source.get("deleted_at")]
    storage_objects = [
        source
        for source in active_sources
        if source.get("storage_bucket") or source.get("storage_path")
    ]
    return {
        "sources_to_delete": len(active_sources),
        "facts_to_delete": _count_rows(db, "extracted_facts", workspace_id),
        "rules_to_delete": _count_rows(db, "business_rules", workspace_id),
        "query_audits_to_anonymize": _count_rows(db, "query_audits", workspace_id),
        "audit_records_to_retain": _count_rows(db, "audit_logs", workspace_id),
        "storage_objects_to_delete": len(storage_objects),
        "pending_storage_delete": bool(storage_objects),
    }


def build_export_report(db: Client, workspace_id: str) -> dict[str, Any]:
    return {
        "sources_exported": _count_rows(db, "sources", workspace_id),
        "facts_exported": _count_rows(db, "extracted_facts", workspace_id),
        "rules_exported": _count_rows(db, "business_rules", workspace_id),
        "query_audits_exported": _count_rows(db, "query_audits", workspace_id),
        "audit_records_exported": _count_rows(db, "audit_logs", workspace_id),
        "storage_export": "metadata_only",
        "storage_delete": "not_applicable",
    }


def execute_metadata_delete(db: Client, workspace_id: str, request_id: str) -> dict[str, Any]:
    sources = _workspace_rows(db, "sources", workspace_id)
    active_sources = [source for source in sources if not source.get("deleted_at")]
    deleted_at = datetime.now(UTC).isoformat()
    pending_storage_delete = False

    for source in active_sources:
        pending_storage_delete = pending_storage_delete or bool(
            source.get("storage_bucket") or source.get("storage_path")
        )
        metadata = dict(source.get("metadata") or {})
        metadata.update(
            {
                "privacy_deleted_by_request_id": request_id,
                "pending_storage_delete": bool(source.get("storage_bucket") or source.get("storage_path")),
            }
        )
        (
            db.table("sources")
            .update({"deleted_at": deleted_at, "metadata": metadata})
            .eq("id", source["id"])
            .eq("workspace_id", workspace_id)
            .execute()
        )

    query_audits_anonymized = _anonymize_query_audits(db, workspace_id, request_id)
    return {
        "sources_metadata_deleted": len(active_sources),
        "facts_deleted": 0,
        "rules_deleted": 0,
        "query_audits_anonymized": query_audits_anonymized,
        "pending_storage_delete": pending_storage_delete,
        "storage_delete": "pending_storage_delete" if pending_storage_delete else "not_applicable",
    }


def audit_privacy_action(
    db: Client,
    *,
    workspace_id: str,
    actor_user_id: str,
    action: str,
    request_id: str,
    metadata: dict[str, Any],
) -> None:
    db.table("audit_logs").insert(
        {
            "workspace_id": workspace_id,
            "actor_user_id": actor_user_id,
            "action": action,
            "resource_type": "privacy_request",
            "resource_id": request_id,
            "metadata": metadata,
        }
    ).execute()


def _count_rows(db: Client, table: str, workspace_id: str) -> int:
    result = (
        cast(Any, db.table(table))
        .select("id", count="exact")
        .eq("workspace_id", workspace_id)
        .execute()
    )
    count = getattr(result, "count", None)
    return int(count) if count is not None else len(_rows(result.data))


def _anonymize_query_audits(db: Client, workspace_id: str, request_id: str) -> int:
    existing = _count_rows(db, "query_audits", workspace_id)
    if existing == 0:
        return 0
    (
        db.table("query_audits")
        .update(
            {
                "user_id": None,
                "question": "[privacy_deleted]",
                "answer": "[privacy_deleted]",
                "prompt_version": f"privacy_deleted:{request_id}",
            }
        )
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return existing


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _workspace_rows(db: Client, table: str, workspace_id: str) -> list[dict[str, Any]]:
    rows = db.table(table).select("*").eq("workspace_id", workspace_id).execute().data
    return _rows(rows)
