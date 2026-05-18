from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_publish_role,
    require_review_role,
)
from context_builder.schemas.review import (
    ActionResponse,
    ApproveRequest,
    ChunkDetailResponse,
    EditFactRequest,
    EditRuleRequest,
    RejectRequest,
    ReviewQueueResponse,
)
from context_builder.services import review_service
from supabase import Client

router = APIRouter()


@router.get("", response_model=ReviewQueueResponse)
async def list_review_queue(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    fact_type: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ReviewQueueResponse:
    result = review_service.get_review_queue(
        db,
        workspace_id=workspace_id,
        page=page,
        per_page=per_page,
        fact_type=fact_type,
        source_id=source_id,
    )
    return ReviewQueueResponse(**result)


@router.get("/{chunk_id}", response_model=ChunkDetailResponse)
async def get_chunk_detail(
    workspace_id: str,
    chunk_id: UUID,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ChunkDetailResponse:
    result = review_service.get_chunk_detail(
        db, workspace_id=workspace_id, chunk_id=str(chunk_id),
    )
    return ChunkDetailResponse(**result)


@router.post("/facts/{fact_id}/approve", response_model=ActionResponse)
async def approve_fact(
    workspace_id: str,
    fact_id: UUID,
    body: ApproveRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.approve_fact(
        db,
        workspace_id=workspace_id,
        fact_id=str(fact_id),
        actor_user_id=membership["user"]["id"],
        note=body.note,
    )
    return ActionResponse(**result)


@router.post("/facts/{fact_id}/reject", response_model=ActionResponse)
async def reject_fact(
    workspace_id: str,
    fact_id: UUID,
    body: RejectRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.reject_fact(
        db,
        workspace_id=workspace_id,
        fact_id=str(fact_id),
        actor_user_id=membership["user"]["id"],
        reason=body.reason,
        note=body.note,
    )
    return ActionResponse(**result)


@router.post("/facts/{fact_id}/publish", response_model=ActionResponse)
async def publish_fact(
    workspace_id: str,
    fact_id: UUID,
    membership: dict[str, Any] = Depends(require_publish_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.publish_fact(
        db,
        workspace_id=workspace_id,
        fact_id=str(fact_id),
        actor_user_id=membership["user"]["id"],
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/publish", response_model=ActionResponse)
async def publish_rule(
    workspace_id: str,
    rule_id: UUID,
    membership: dict[str, Any] = Depends(require_publish_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.publish_rule(
        db,
        workspace_id=workspace_id,
        rule_id=str(rule_id),
        actor_user_id=membership["user"]["id"],
    )
    return ActionResponse(**result)


@router.post("/facts/{fact_id}/edit", response_model=ActionResponse)
async def edit_fact(
    workspace_id: str,
    fact_id: UUID,
    body: EditFactRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.edit_fact(
        db,
        workspace_id=workspace_id,
        fact_id=str(fact_id),
        actor_user_id=membership["user"]["id"],
        new_content=body.content,
        note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/approve", response_model=ActionResponse)
async def approve_rule(
    workspace_id: str,
    rule_id: UUID,
    body: ApproveRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.approve_rule(
        db,
        workspace_id=workspace_id,
        rule_id=str(rule_id),
        actor_user_id=membership["user"]["id"],
        note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/reject", response_model=ActionResponse)
async def reject_rule(
    workspace_id: str,
    rule_id: UUID,
    body: RejectRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.reject_rule(
        db,
        workspace_id=workspace_id,
        rule_id=str(rule_id),
        actor_user_id=membership["user"]["id"],
        reason=body.reason,
        note=body.note,
    )
    return ActionResponse(**result)


@router.post("/rules/{rule_id}/edit", response_model=ActionResponse)
async def edit_rule(
    workspace_id: str,
    rule_id: UUID,
    body: EditRuleRequest,
    membership: dict[str, Any] = Depends(require_review_role),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ActionResponse:
    result = review_service.edit_rule(
        db,
        workspace_id=workspace_id,
        rule_id=str(rule_id),
        actor_user_id=membership["user"]["id"],
        new_condition=body.condition,
        new_action=body.action,
        note=body.note,
    )
    return ActionResponse(**result)
