from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_upload_permission,
    require_workspace_member,
)
from context_builder.schemas.tutorial import (
    TutorialMessageRequest,
    TutorialResponse,
    TutorialToolConfirmationRequest,
)
from context_builder.services.context_build_tutor import ContextBuildTutor, TutorCompileResult
from context_builder.services.context_build_use_cases import compile_context_build_run
from supabase import Client

router = APIRouter()


def get_context_build_tutor(
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> ContextBuildTutor:
    def compile_executor(**kwargs: Any) -> TutorCompileResult:
        run_id = kwargs.get("context_build_run_id")
        if not isinstance(run_id, str) or not run_id:
            return TutorCompileResult(status="failed", error="context_build_run_id_required")
        run = compile_context_build_run(
            db,
            workspace_id=str(kwargs["workspace_id"]),
            run_id=run_id,
            confirmed=True,
        )
        return TutorCompileResult(
            status=run.status,
            context_build_run_id=run.id,
            bundle_hash=run.bundle_hash,
            context_version=run.context_version,
        )

    return ContextBuildTutor(compile_executor=compile_executor)


@router.post("/messages", response_model=TutorialResponse)
async def create_tutorial_message(
    request: TutorialMessageRequest,
    membership: dict[str, Any] = Depends(require_workspace_member),
    tutor: ContextBuildTutor = Depends(get_context_build_tutor),
) -> TutorialResponse:
    response = tutor.reply_to_message(
        request,
        workspace_id=str(membership["workspace_id"]),
        actor_user_id=str(membership["user"]["id"]),
    )
    _raise_for_unavailable_compile(response)
    return response


@router.post("/tool-confirmations", response_model=TutorialResponse)
async def confirm_tutorial_tool(
    request: TutorialToolConfirmationRequest,
    membership: dict[str, Any] = Depends(require_upload_permission),
    tutor: ContextBuildTutor = Depends(get_context_build_tutor),
) -> TutorialResponse:
    response = tutor.confirm_tool(
        request,
        workspace_id=str(membership["workspace_id"]),
        actor_user_id=str(membership["user"]["id"]),
    )
    _raise_for_unavailable_compile(response)
    return response


def _raise_for_unavailable_compile(response: TutorialResponse) -> None:
    if any(call.status == "unavailable" for call in response.tool_calls):
        raise HTTPException(status_code=409, detail=response.tool_calls[0].result)
