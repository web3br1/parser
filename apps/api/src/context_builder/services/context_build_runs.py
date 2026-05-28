from __future__ import annotations

from typing import Any, cast

from context_builder.schemas.context_build import (
    ContextBuildRunCreate,
    ContextBuildRunResponse,
)


def create_context_build_run(
    db: Any,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    payload: ContextBuildRunCreate,
    status: str = "created",
) -> ContextBuildRunResponse:
    row = {
        "workspace_id": workspace_id,
        "actor_user_id": actor_user_id,
        "input_mode": payload.input_mode,
        "status": status,
        "recommended_action": payload.recommended_action,
        "input_fingerprint": payload.input_fingerprint,
        "input_hash": payload.input_hash,
        "source_dir": payload.source_dir,
        "source_pack_id": payload.source_pack_id,
        "source_pack_version": payload.source_pack_version,
        "staged_upload_id": payload.staged_upload_id,
        "source_count": payload.source_count,
        "job_count": payload.job_count,
        "bundle_hash": None,
        "context_version": None,
        "output_path": None,
        "readiness_status": None,
        "readiness_score": None,
        "file_counts": payload.file_counts,
        "missing_files": payload.missing_files,
        "extra_files": payload.extra_files,
        "steps": payload.steps,
        "warnings": payload.warnings,
        "errors": payload.errors,
        "metadata": payload.metadata,
    }
    result = db.table("context_build_runs").insert(row).execute()
    return _response_from_result(result, "context_build_run_create_failed")


def list_context_build_runs(db: Any, *, workspace_id: str) -> list[ContextBuildRunResponse]:
    result = (
        db.table("context_build_runs")
        .select("*")
        .eq("workspace_id", workspace_id)
        .order("created_at", desc=True)
        .execute()
    )
    data = getattr(result, "data", None)
    if not isinstance(data, list):
        return []
    return [ContextBuildRunResponse(**cast(dict[str, Any], row)) for row in data]


def get_context_build_run(
    db: Any,
    *,
    workspace_id: str,
    run_id: str,
) -> ContextBuildRunResponse | None:
    result = (
        db.table("context_build_runs")
        .select("*")
        .eq("id", run_id)
        .eq("workspace_id", workspace_id)
        .maybe_single()
        .execute()
    )
    data = getattr(result, "data", None)
    if not isinstance(data, dict):
        return None
    return ContextBuildRunResponse(**data)


def update_context_build_run_compiled(
    db: Any,
    *,
    workspace_id: str,
    run_id: str,
    bundle_hash: str,
    context_version: str,
    output_path: str,
    readiness_status: str,
    readiness_score: int,
    warnings: list[str],
) -> ContextBuildRunResponse:
    result = (
        db.table("context_build_runs")
        .update(
            {
                "status": "compiled",
                "bundle_hash": bundle_hash,
                "context_version": context_version,
                "output_path": output_path,
                "readiness_status": readiness_status,
                "readiness_score": readiness_score,
                "warnings": warnings,
                "errors": [],
            }
        )
        .eq("id", run_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _response_from_result(result, "context_build_run_update_failed")


def update_context_build_run_failed(
    db: Any,
    *,
    workspace_id: str,
    run_id: str,
    error: str,
) -> ContextBuildRunResponse:
    result = (
        db.table("context_build_runs")
        .update({"status": "failed", "errors": [error]})
        .eq("id", run_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _response_from_result(result, "context_build_run_update_failed")


def _response_from_result(result: Any, error: str) -> ContextBuildRunResponse:
    data = getattr(result, "data", None)
    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        raise RuntimeError(error)
    return ContextBuildRunResponse(**cast(dict[str, Any], row))
