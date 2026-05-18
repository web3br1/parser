from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.schemas.query import QueryRequest, QueryResponse
from context_builder.services import query_service
from supabase import Client

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def post_query(
    workspace_id: str,
    body: QueryRequest,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> QueryResponse:
    result = query_service.answer_query(
        db,
        workspace_id=workspace_id,
        question=body.question,
        actor_user_id=membership["user"]["id"],
        user_role=membership["role"],
        max_output_tokens=body.max_output_tokens,
        include_evidence=body.include_evidence,
    )
    return QueryResponse(**result)
