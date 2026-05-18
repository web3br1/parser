from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException

from context_builder.dependencies import get_current_user, get_supabase_service_for_backend_only
from context_builder.schemas.workspace import WorkspaceCreate, WorkspaceResponse
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


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> WorkspaceResponse:
    """Cria workspace e adiciona o criador como owner via RPC transacional."""
    rpc_result = db.rpc(
        "create_workspace_with_owner",
        {
            "workspace_name": body.name,
            "workspace_slug": body.slug,
            "workspace_settings": {},
            "actor_user_id": current_user["id"],
        },
    ).execute()
    workspace_id = rpc_result.data
    if isinstance(workspace_id, list):
        workspace_id = workspace_id[0] if workspace_id else None
    if not workspace_id:
        raise HTTPException(status_code=500, detail="workspace_create_failed")

    workspace_result = cast(Any, (
        db.table("workspaces")
        .select("*")
        .eq("id", workspace_id)
        .maybe_single()
        .execute()
    ))
    workspace = _row(workspace_result.data)
    if not workspace:
        raise HTTPException(status_code=500, detail="workspace_lookup_failed")

    return _workspace_response(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> list[WorkspaceResponse]:
    result = (
        db.table("workspace_members")
        .select("workspace_id, workspaces(*)")
        .eq("user_id", current_user["id"])
        .execute()
    )
    workspaces = []
    for row in _rows(result.data):
        workspace = _row(row.get("workspaces"))
        if workspace is not None:
            workspaces.append(_workspace_response(workspace))
    return workspaces


def _workspace_response(row: dict[str, Any]) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=row["id"],
        name=row["name"],
        slug=row.get("slug"),
        status=row["status"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
