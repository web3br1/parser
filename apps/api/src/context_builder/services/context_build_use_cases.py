from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from source_pack.compiler import compile_source_pack
from source_pack.writer import write_bundle

from context_builder.schemas.context_build import (
    ContextBuildFileMetadata,
    ContextBuildMode,
    ContextBuildPreflightRequest,
    ContextBuildPreflightResponse,
    ContextBuildRecommendedAction,
    ContextBuildRunCreate,
    ContextBuildRunResponse,
    ContextBuildStatus,
)
from context_builder.services.context_build_runs import (
    create_context_build_run,
    get_context_build_run,
    update_context_build_run_compiled,
    update_context_build_run_failed,
)
from context_builder.services.context_build_staging import (
    StagedUpload,
    resolve_staged_upload,
)
from context_builder.services.source_pack_import_runs import source_pack_input_hash
from context_builder.services.source_pack_preflight import inspect_source_pack_upload

DEFAULT_ALLOWED_SOURCE_ROOTS = (Path(r"C:\tmp\context-builder-sources"),)


def preflight_context_build_run(
    db: Any,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    payload: ContextBuildPreflightRequest,
) -> ContextBuildPreflightResponse:
    response = _detect(workspace_id, payload)
    if not payload.persist:
        return response
    run = create_context_build_run(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        payload=ContextBuildRunCreate(
            input_mode=response.input_mode,
            input_fingerprint=response.input_fingerprint,
            input_hash=response.input_hash,
            recommended_action=response.recommended_action,
            source_dir=str(resolve_allowed_source_dir(payload.source_dir))
            if payload.source_dir
            else None,
            source_pack_id=response.source_pack_id,
            source_pack_version=response.source_pack_version,
            staged_upload_id=payload.staged_upload_id,
            source_count=response.counts.get("file_count", 0),
            file_counts=response.counts,
            missing_files=response.missing_files,
            extra_files=response.extra_files,
            warnings=response.warnings,
            errors=response.errors,
            metadata=response.metadata,
        ),
        status=response.status,
    )
    return response.model_copy(update={"run_id": run.id})


def create_context_build_run_from_request(
    db: Any,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    payload: ContextBuildRunCreate,
) -> ContextBuildRunResponse:
    if payload.source_dir:
        payload = payload.model_copy(
            update={"source_dir": str(resolve_allowed_source_dir(payload.source_dir))}
        )
    return create_context_build_run(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def compile_context_build_run(
    db: Any,
    *,
    workspace_id: str,
    run_id: str,
    confirmed: bool,
) -> ContextBuildRunResponse:
    if not confirmed:
        raise HTTPException(
            status_code=409,
            detail={"code": "confirmation_required"},
        )
    run = get_context_build_run(db, workspace_id=workspace_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="context_build_run_not_found")
    if run.input_mode != "source_pack":
        raise HTTPException(
            status_code=409,
            detail={"code": "compile_not_available_for_input_mode"},
        )
    if run.status != "preflighted" or run.recommended_action != "compile_as_source_pack":
        raise HTTPException(
            status_code=409,
            detail={"code": "context_build_run_not_compilable"},
        )
    if run.staged_upload_id:
        staged = resolve_staged_upload(
            workspace_id=workspace_id,
            staged_upload_id=run.staged_upload_id,
        )
        source_dir = staged.source_root
    elif run.source_dir:
        source_dir = resolve_allowed_source_dir(run.source_dir)
    else:
        raise HTTPException(status_code=409, detail={"code": "source_dir_required"})

    try:
        bundle = compile_source_pack(source_dir)
        output_path = source_dir / f"{source_dir.name}.context_bundle.v1.json"
        write_result = write_bundle(bundle, output_path)
        return update_context_build_run_compiled(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            bundle_hash=bundle.integrity.bundle_hash,
            context_version=bundle.context_version,
            output_path=_public_output_path(run=run, output_path=write_result.path),
            readiness_status=bundle.readiness.status,
            readiness_score=bundle.readiness.score,
            warnings=bundle.readiness.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        update_context_build_run_failed(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            error=type(exc).__name__,
        )
        raise


def _detect(
    workspace_id: str,
    payload: ContextBuildPreflightRequest,
) -> ContextBuildPreflightResponse:
    if payload.staged_upload_id:
        staged = resolve_staged_upload(
            workspace_id=workspace_id,
            staged_upload_id=payload.staged_upload_id,
        )
        return _detect_staged_upload(staged)
    if payload.source_dir:
        source_dir = resolve_allowed_source_dir(payload.source_dir)
        source_pack = inspect_source_pack_upload(source_dir)
        if source_pack.is_source_pack:
            status: ContextBuildStatus = (
                "preflighted" if source_pack.recommended_action != "reject" else "rejected"
            )
            input_hash = (
                source_pack_input_hash(source_dir)
                if source_pack.status == "complete"
                else None
            )
            return ContextBuildPreflightResponse(
                status=status,
                input_mode="source_pack",
                recommended_action=source_pack.recommended_action,
                input_fingerprint=source_dir_fingerprint(source_dir),
                input_hash=input_hash,
                source_dir=None,
                source_pack_id=source_pack.source_pack_id,
                source_pack_version=source_pack.source_pack_version,
                counts={
                    "file_count": source_pack.numbered_source_count,
                    "csv_count": source_pack.csv_count,
                    "markdown_count": source_pack.markdown_count,
                    "manifest_document_count": source_pack.manifest_document_count,
                    "official_reference_count": source_pack.official_reference_count,
                },
                missing_files=source_pack.missing_files,
                extra_files=source_pack.extra_files,
                errors=source_pack.errors,
                metadata={
                    "is_source_pack": True,
                    "preflight_status": source_pack.status,
                    "readme_present": source_pack.readme_present,
                    "language": source_pack.language,
                    "publication_status": source_pack.publication_status,
                },
            )
        files = _files_from_source_dir(source_dir)
        return _detect_files(
            files,
            source_dir=str(source_dir),
            input_fingerprint=payload.input_fingerprint,
        )
    return _detect_files(payload.files, input_fingerprint=payload.input_fingerprint)


def _detect_staged_upload(staged: StagedUpload) -> ContextBuildPreflightResponse:
    source_pack = inspect_source_pack_upload(staged.source_root)
    if source_pack.is_source_pack:
        status: ContextBuildStatus = (
            "preflighted" if source_pack.recommended_action != "reject" else "rejected"
        )
        blocking_reasons = _source_pack_blocking_reasons(source_pack)
        return ContextBuildPreflightResponse(
            status=status,
            input_mode="source_pack",
            recommended_action=source_pack.recommended_action,
            input_fingerprint=staged.input_fingerprint,
            input_hash=staged.input_hash,
            source_dir=None,
            source_pack_id=source_pack.source_pack_id,
            source_pack_version=source_pack.source_pack_version,
            counts={
                "file_count": source_pack.numbered_source_count,
                "csv_count": source_pack.csv_count,
                "markdown_count": source_pack.markdown_count,
                "manifest_document_count": source_pack.manifest_document_count,
                "official_reference_count": source_pack.official_reference_count,
            },
            missing_files=source_pack.missing_files,
            extra_files=source_pack.extra_files,
            errors=source_pack.errors,
            blocking_reasons=blocking_reasons,
            metadata={
                "is_source_pack": True,
                "preflight_status": source_pack.status,
                "readme_present": source_pack.readme_present,
                "language": source_pack.language,
                "publication_status": source_pack.publication_status,
                "staged_upload_id": staged.staged_upload_id,
            },
        )
    return _detect_files(
        staged.files,
        input_fingerprint=staged.input_fingerprint,
    ).model_copy(
        update={
            "input_hash": staged.input_hash,
            "metadata": {"is_source_pack": False, "staged_upload_id": staged.staged_upload_id},
        }
    )


def _source_pack_blocking_reasons(source_pack: Any) -> list[str]:
    reasons = list(source_pack.errors)
    if source_pack.missing_files:
        reasons.append("missing_files")
    if source_pack.extra_files:
        reasons.append("extra_files")
    if source_pack.recommended_action == "reject" and not reasons:
        reasons.append("source_pack_rejected")
    return reasons


def _public_output_path(*, run: ContextBuildRunResponse, output_path: Path) -> str:
    if run.staged_upload_id:
        return f"staged_upload:{run.staged_upload_id}/{output_path.name}"
    return str(output_path)


def resolve_allowed_source_dir(source_dir: str) -> Path:
    requested = Path(source_dir).expanduser().resolve()
    allowed_roots = _allowed_source_roots()
    if not any(_is_relative_to(requested, root) for root in allowed_roots):
        raise HTTPException(
            status_code=403,
            detail={"code": "source_dir_not_allowed"},
        )
    return requested


def _allowed_source_roots() -> tuple[Path, ...]:
    configured = os.environ.get("CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS", "")
    roots = [
        Path(raw.strip()).expanduser().resolve()
        for raw in configured.split(os.pathsep)
        if raw.strip()
    ]
    if not roots:
        roots = [root.resolve() for root in DEFAULT_ALLOWED_SOURCE_ROOTS]
    return tuple(roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _detect_files(
    files: list[ContextBuildFileMetadata],
    *,
    source_dir: str | None = None,
    input_fingerprint: str | None = None,
) -> ContextBuildPreflightResponse:
    sorted_files = sorted(files, key=lambda item: item.relative_path or item.name)
    counts = _file_counts(sorted_files)
    if not sorted_files:
        return ContextBuildPreflightResponse(
            status="rejected",
            input_mode="multi_document_batch",
            recommended_action="reject",
            input_fingerprint=input_fingerprint or "files:empty",
            source_dir=None,
            counts=counts,
            errors=["no_files"],
            blocking_reasons=["no_files"],
        )
    if any(_normalized_basename(item) == "00_source_manifest.md" for item in sorted_files):
        return ContextBuildPreflightResponse(
            status="preflighted",
            input_mode="source_pack",
            recommended_action="compile_as_source_pack",
            input_fingerprint=input_fingerprint or _files_fingerprint(sorted_files),
            source_dir=None,
            counts=counts,
            warnings=["source_pack_metadata_detected"],
            errors=[] if source_dir else ["source_pack_staging_required"],
            blocking_reasons=[] if source_dir else ["source_pack_staging_required"],
            metadata={
                "is_source_pack": True,
                "preflight_status": "metadata_only",
                "authoritative_content_check": source_dir is not None,
            },
        )
    input_mode: ContextBuildMode = (
        "single_document" if len(sorted_files) == 1 else "multi_document_batch"
    )
    recommended_action: ContextBuildRecommendedAction = (
        "normal_ingest" if input_mode == "single_document" else "batch_ingest"
    )
    return ContextBuildPreflightResponse(
        status="preflighted",
        input_mode=input_mode,
        recommended_action=recommended_action,
        input_fingerprint=input_fingerprint or _files_fingerprint(sorted_files),
        source_dir=None,
        counts=counts,
        metadata={"is_source_pack": False},
    )


def _files_from_source_dir(source_dir: Path) -> list[ContextBuildFileMetadata]:
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    return [
        ContextBuildFileMetadata(
            name=path.name,
            size=path.stat().st_size,
            relative_path=path.relative_to(source_dir).as_posix(),
        )
        for path in source_dir.iterdir()
        if path.is_file()
    ]


def _file_counts(files: list[ContextBuildFileMetadata]) -> dict[str, int]:
    csv_count = sum(1 for item in files if Path(item.name).suffix.lower() == ".csv")
    markdown_count = sum(1 for item in files if Path(item.name).suffix.lower() == ".md")
    return {
        "file_count": len(files),
        "csv_count": csv_count,
        "markdown_count": markdown_count,
    }


def _normalized_basename(item: ContextBuildFileMetadata) -> str:
    return Path(item.relative_path or item.name).name.strip().casefold()


def _files_fingerprint(files: list[ContextBuildFileMetadata]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update((item.relative_path or item.name).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item.size).encode("ascii"))
        digest.update(b"\0")
    return f"files:{digest.hexdigest()}"


def source_dir_fingerprint(source_dir: Path) -> str:
    digest = hashlib.sha256(str(source_dir).encode("utf-8")).hexdigest()
    return f"source_dir:{digest}"
