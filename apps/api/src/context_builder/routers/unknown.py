from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from context_builder.dependencies import (
    get_current_user,
    get_supabase_service_for_backend_only,
    require_review_role,
)
from context_builder.schemas.review import (
    IgnoreRequest,
    IgnoreResponse,
    ReclassifyRequest,
    ReclassifyResponse,
    UnknownQueueResponse,
)
from context_builder.services import unknown_service
from supabase import Client

router = APIRouter()


@router.get("", response_model=UnknownQueueResponse)
async def list_unknown_queue(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> UnknownQueueResponse:
    result = unknown_service.get_unknown_queue(
        db,
        workspace_id=workspace_id,
        page=page,
        per_page=per_page,
        status_filter=status,
    )
    return UnknownQueueResponse(**result)


@router.post("/{item_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_unknown(
    workspace_id: str,
    item_id: UUID,
    body: ReclassifyRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    user: dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ReclassifyResponse:
    result = unknown_service.reclassify_unknown(
        db,
        workspace_id=workspace_id,
        item_id=str(item_id),
        fact_type=body.fact_type,
        destination=body.destination,
        reviewer_id=user["id"],
        note=body.note,
    )
    return ReclassifyResponse(**result)


@router.post("/{item_id}/ignore", response_model=IgnoreResponse)
async def ignore_unknown(
    workspace_id: str,
    item_id: UUID,
    body: IgnoreRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    user: dict[str, Any] = Depends(get_current_user),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> IgnoreResponse:
    result = unknown_service.ignore_unknown(
        db,
        workspace_id=workspace_id,
        item_id=str(item_id),
        reviewer_id=user["id"],
        note=body.note,
    )
    return IgnoreResponse(**result)
