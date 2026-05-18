from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.schemas.knowledge import KnowledgeListResponse
from context_builder.services import knowledge_service
from supabase import Client

router = APIRouter()


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(
    workspace_id: str,
    record_type: str = Query(default="all", pattern="^(all|facts|rules)$"),
    kind_filter: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> KnowledgeListResponse:
    result = knowledge_service.list_published_records(
        db,
        workspace_id=workspace_id,
        record_type=record_type,
        kind_filter=kind_filter,
        source_id=source_id,
        page=page,
        per_page=per_page,
    )
    return KnowledgeListResponse(**result)
