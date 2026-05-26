from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_upload_permission,
    require_workspace_member,
)
from context_builder.schemas.context_build import (
    ContextBuildCompileRequest,
    ContextBuildPreflightRequest,
    ContextBuildPreflightResponse,
    ContextBuildRunCreate,
    ContextBuildRunResponse,
)
from context_builder.services.context_build_runs import (
    get_context_build_run,
    list_context_build_runs,
)
from context_builder.services.context_build_use_cases import (
    compile_context_build_run,
    create_context_build_run_from_request,
    preflight_context_build_run,
)
from supabase import Client

router = APIRouter()


@router.post("/preflight", response_model=ContextBuildPreflightResponse)
async def preflight_context_build(
    payload: ContextBuildPreflightRequest,
    membership: dict[str, Any] = Depends(require_upload_permission),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBuildPreflightResponse:
    return preflight_context_build_run(
        db,
        workspace_id=membership["workspace_id"],
        actor_user_id=membership["user"]["id"],
        payload=payload,
    )


@router.post("", response_model=ContextBuildRunResponse, status_code=201)
async def create_context_build(
    payload: ContextBuildRunCreate,
    membership: dict[str, Any] = Depends(require_upload_permission),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBuildRunResponse:
    return create_context_build_run_from_request(
        db,
        workspace_id=membership["workspace_id"],
        actor_user_id=membership["user"]["id"],
        payload=payload,
    )


@router.get("", response_model=list[ContextBuildRunResponse])
async def list_context_build(
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> list[ContextBuildRunResponse]:
    return list_context_build_runs(db, workspace_id=membership["workspace_id"])


@router.get("/{run_id}", response_model=ContextBuildRunResponse)
async def get_context_build(
    run_id: str,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBuildRunResponse:
    run = get_context_build_run(
        db,
        workspace_id=membership["workspace_id"],
        run_id=run_id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="context_build_run_not_found")
    return run


@router.post("/{run_id}/actions/compile", response_model=ContextBuildRunResponse)
async def compile_context_build(
    run_id: str,
    payload: ContextBuildCompileRequest,
    membership: dict[str, Any] = Depends(require_upload_permission),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBuildRunResponse:
    return compile_context_build_run(
        db,
        workspace_id=membership["workspace_id"],
        run_id=run_id,
        confirmed=bool(payload.confirmed or payload.confirmation),
    )
