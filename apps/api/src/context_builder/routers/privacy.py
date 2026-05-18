from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.services.privacy_service import (
    DELETE_CONFIRMATION_PHRASE,
    audit_privacy_action,
    build_export_report,
    build_privacy_plan,
    execute_metadata_delete,
)
from supabase import Client

router = APIRouter()


def _row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    return None


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _require_owner(membership: dict[str, Any]) -> None:
    if membership["role"] != "owner":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": ["owner"],
                "current": membership["role"],
            },
        )


def _response(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    response = {
        "request_id": row["id"],
        "request_type": row["request_type"],
        "status": row["status"],
        "dry_run": bool(metadata.get("dry_run", row["status"] == "dry_run")),
        "deletion_plan": row["dry_run_plan"],
    }
    if "report" in metadata:
        response["report"] = metadata["report"]
    return response


@router.post("/export", status_code=202)
async def create_export_request(
    workspace_id: str,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> dict[str, Any]:
    _require_owner(membership)
    report = build_export_report(db, workspace_id)
    insert_rows = (
        db.table("privacy_requests")
        .insert(
            {
                "workspace_id": workspace_id,
                "requested_by": membership["user"]["id"],
                "request_type": "export",
                "status": "completed",
                "dry_run_plan": {},
                "confirmation_required": False,
                "metadata": {"dry_run": False, "confirmed": True, "report": report},
            }
        )
        .execute()
        .data
    )
    row = _rows(insert_rows)[0] if _rows(insert_rows) else None
    if row is None:
        raise HTTPException(status_code=500, detail="privacy_request_create_failed")
    audit_privacy_action(
        db,
        workspace_id=workspace_id,
        actor_user_id=membership["user"]["id"],
        action="privacy.export.completed",
        request_id=row["id"],
        metadata={"report": report},
    )
    return _response(row)


@router.post("/delete-request", status_code=202)
async def create_delete_request(
    workspace_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> dict[str, Any]:
    _require_owner(membership)
    confirmed = bool(body.get("confirmed"))
    if confirmed:
        raise HTTPException(status_code=400, detail="use_delete_confirmation_endpoint")
    plan = build_privacy_plan(db, workspace_id)
    insert_rows = (
        db.table("privacy_requests")
        .insert(
            {
                "workspace_id": workspace_id,
                "requested_by": membership["user"]["id"],
                "request_type": "delete",
                "status": "dry_run",
                "dry_run_plan": plan,
                "confirmation_required": True,
                "metadata": {"dry_run": True, "confirmed": False},
            }
        )
        .execute()
        .data
    )
    row = _rows(insert_rows)[0] if _rows(insert_rows) else None
    if row is None:
        raise HTTPException(status_code=500, detail="privacy_request_create_failed")
    audit_privacy_action(
        db,
        workspace_id=workspace_id,
        actor_user_id=membership["user"]["id"],
        action="privacy.delete.dry_run",
        request_id=row["id"],
        metadata={"deletion_plan": plan},
    )
    return _response(row)


@router.post("/delete-request/{request_id}/confirm", status_code=202)
async def confirm_delete_request(
    workspace_id: str,
    request_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> dict[str, Any]:
    _require_owner(membership)
    if body.get("confirmation") != DELETE_CONFIRMATION_PHRASE:
        raise HTTPException(status_code=400, detail="invalid_delete_confirmation")
    existing = _get_privacy_request(db, workspace_id, request_id)
    if not existing or existing["request_type"] != "delete":
        raise HTTPException(status_code=404, detail="privacy_request_not_found")
    if existing["status"] in {"completed", "processing"} and existing.get("metadata", {}).get("confirmed"):
        return _response(existing)

    report = execute_metadata_delete(db, workspace_id, request_id)
    metadata = dict(existing.get("metadata") or {})
    metadata.update({"dry_run": False, "confirmed": True, "report": report})
    final_status = "processing" if report.get("pending_storage_delete") else "completed"
    audit_action = (
        "privacy.delete.pending_storage"
        if report.get("pending_storage_delete")
        else "privacy.delete.completed"
    )
    update_result = (
        db.table("privacy_requests")
        .update(
            {
                "status": final_status,
                "confirmation_required": False,
                "metadata": metadata,
            }
        )
        .eq("id", request_id)
        .eq("workspace_id", workspace_id)
        .execute()
        .data
    )
    updated_rows = _rows(update_result)
    updated = (
        updated_rows[0]
        if updated_rows
        else {**existing, "status": final_status, "confirmation_required": False, "metadata": metadata}
    )
    audit_privacy_action(
        db,
        workspace_id=workspace_id,
        actor_user_id=membership["user"]["id"],
        action=audit_action,
        request_id=request_id,
        metadata={"report": report},
    )
    return _response(updated)


@router.get("/delete-request/{request_id}")
async def get_delete_request(
    workspace_id: str,
    request_id: str,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> dict[str, Any]:
    _require_owner(membership)
    row = _get_privacy_request(db, workspace_id, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="privacy_request_not_found")
    return _response(row)


def _get_privacy_request(db: Client, workspace_id: str, request_id: str) -> dict[str, Any] | None:
    result = cast(Any, (
        db.table("privacy_requests")
        .select("*")
        .eq("id", request_id)
        .eq("workspace_id", workspace_id)
        .maybe_single()
        .execute()
    ))
    return _row(result.data)
