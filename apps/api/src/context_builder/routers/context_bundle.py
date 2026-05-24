from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.schemas.context_bundle import ContextBundleResponse
from context_builder.services.context_bundle_service import build_context_bundle
from supabase import Client

router = APIRouter()


@router.get("", response_model=ContextBundleResponse)
async def get_context_bundle(
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBundleResponse:
    return build_context_bundle(
        db,
        workspace_id=str(membership["workspace_id"]),
        actor_user_id=str(membership["user"]["id"]),
        actor_role=str(membership["role"]),
    )
