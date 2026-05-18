import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from observability.logging import get_logger
from security.file_validator import validate_file

from context_builder.config import get_settings
from context_builder.dependencies import (
    get_supabase_service_for_backend_only,
    require_upload_permission,
    require_workspace_member,
)
from context_builder.schemas.job import JobStatusResponse
from context_builder.schemas.source import SourceResponse, UploadResponse
from context_builder.services.ingest_queue import create_and_enqueue_ingest_job
from context_builder.services.storage import delete_from_storage, upload_to_storage
from supabase import Client

router = APIRouter()
logger = get_logger("api")


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


async def _read_upload_to_spooled_file(
    file: UploadFile,
    *,
    max_file_size_bytes: int,
) -> tempfile.SpooledTemporaryFile[bytes]:
    total_size = 0
    spooled_file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_file_size_bytes:
            spooled_file.close()
            raise HTTPException(status_code=413, detail="file_too_large")
        spooled_file.write(chunk)
    spooled_file.seek(0)
    return spooled_file


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_source(
    file: UploadFile = File(...),
    membership: dict[str, Any] = Depends(require_upload_permission),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> UploadResponse:
    workspace_id = membership["workspace_id"]
    user_id = membership["user"]["id"]
    settings = get_settings()
    logger.info("api_upload_started", workspace_id=workspace_id)

    # MVP: leitura completa em memória. Limite 50 MB.
    # V1: migrar para streaming com SpooledTemporaryFile.
    spooled_file = await _read_upload_to_spooled_file(
        file,
        max_file_size_bytes=settings.max_file_size_bytes,
    )
    try:
        content = spooled_file.read()
    finally:
        spooled_file.close()

    file_hash = hashlib.sha256(content).hexdigest()
    existing = (
        db.table("sources")
        .select("id, status")
        .eq("workspace_id", workspace_id)
        .eq("file_hash", file_hash)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    existing_data = _row(getattr(existing, "data", None))
    if existing_data:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_file",
                "existing_source_id": existing_data["id"],
                "existing_status": existing_data["status"],
            },
        )

    declared_mime = file.content_type or "application/octet-stream"
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix or ""
    _validate_upload_content(content, suffix, declared_mime)

    detected_mime = declared_mime
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        validation = validate_file(tmp_path, declared_mime)
        detected_mime = validation.detected_mime or declared_mime
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
            logger.info("temp_file_deleted", workspace_id=workspace_id)
        except Exception as exc:
            logger.warning(
                "temp_file_cleanup_failed",
                workspace_id=workspace_id,
                error_type=type(exc).__name__,
            )

    if not validation.valid:
        reason = validation.reason.value if validation.reason else "unknown"
        raise HTTPException(
            status_code=422,
            detail={"code": "file_validation_failed", "reason": reason},
        )

    source = _create_source(
        db=db,
        workspace_id=workspace_id,
        original_name=original_name,
        detected_mime=detected_mime,
        file_size_bytes=len(content),
        file_hash=file_hash,
        user_id=user_id,
    )
    source_id = source["id"]
    storage_path = f"workspaces/{workspace_id}/sources/{source_id}/original{suffix}"
    storage_uploaded = False

    try:
        upload_to_storage(content=content, path=storage_path, mime_type=detected_mime)
        storage_uploaded = True

        db.table("sources").update(
            {
                "storage_bucket": settings.workspace_storage_bucket,
                "storage_path": storage_path,
            }
        ).eq("id", source_id).execute()

        job_id = create_and_enqueue_ingest_job(
            source_id=source_id,
            workspace_id=workspace_id,
            storage_path=storage_path,
            declared_mime=detected_mime,
            file_hash=file_hash,
            actor_user_id=user_id,
            db=db,
        )
    except HTTPException as exc:
        _rollback_upload(db, source_id, storage_path, storage_uploaded)
        logger.error("api_upload_failed", workspace_id=workspace_id, source_id=source_id)
        raise HTTPException(status_code=500, detail="upload_pipeline_failed") from exc
    except Exception as exc:
        _rollback_upload(db, source_id, storage_path, storage_uploaded)
        logger.exception(
            "api_upload_failed",
            exc,
            workspace_id=workspace_id,
            source_id=source_id,
        )
        raise HTTPException(status_code=500, detail="upload_pipeline_failed") from exc

    logger.info(
        "api_upload_accepted",
        workspace_id=workspace_id,
        source_id=source_id,
        job_id=job_id,
    )
    return UploadResponse(
        source_id=source_id,
        job_id=job_id,
        status="queued",
        message="File accepted. Processing started.",
    )


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> list[SourceResponse]:
    result = (
        db.table("sources")
        .select("*")
        .eq("workspace_id", membership["workspace_id"])
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return [_source_response(row) for row in _rows(result.data)]


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> SourceResponse:
    result = cast(Any, (
        db.table("sources")
        .select("*")
        .eq("id", source_id)
        .eq("workspace_id", membership["workspace_id"])
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    ))
    source = _row(result.data)
    if not source:
        raise HTTPException(status_code=404, detail="source_not_found")
    return _source_response(source)


@router.get("/{source_id}/job", response_model=JobStatusResponse)
async def get_source_job(
    source_id: str,
    membership: dict[str, Any] = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> JobStatusResponse:
    source_result = cast(Any, (
        db.table("sources")
        .select("id")
        .eq("id", source_id)
        .eq("workspace_id", membership["workspace_id"])
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    ))
    if not _row(source_result.data):
        raise HTTPException(status_code=404, detail="job_not_found")

    result = cast(Any, (
        db.table("processing_jobs")
        .select("*")
        .eq("source_id", source_id)
        .eq("workspace_id", membership["workspace_id"])
        .eq("job_type", "ingest")
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    ))
    job = _row(result.data)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")

    metadata = _row(job.get("metadata")) or {}
    return JobStatusResponse(
        job_id=str(job["id"]),
        status=str(job["status"]),
        source_id=source_id,
        started_at=_optional_datetime(cast(datetime | str | None, job.get("started_at"))),
        finished_at=_optional_datetime(cast(datetime | str | None, job.get("finished_at"))),
        error_message=cast(str | None, job.get("error_message")),
        chunks_created=cast(int | None, metadata.get("chunks_created")),
    )


def _validate_upload_content(content: bytes, suffix: str, declared_mime: str) -> None:
    if len(content) == 0:
        return
    if not suffix:
        raise HTTPException(
            status_code=422,
            detail={"code": "file_validation_failed", "reason": "extension_blocked"},
        )
    settings = get_settings()
    if declared_mime not in settings.allowed_mime_types:
        raise HTTPException(
            status_code=422,
            detail={"code": "file_validation_failed", "reason": "mime_mismatch"},
        )


def _create_source(
    *,
    db: Client,
    workspace_id: str,
    original_name: str,
    detected_mime: str,
    file_size_bytes: int,
    file_hash: str,
    user_id: str,
) -> dict[str, Any]:
    try:
        source_result = (
            db.table("sources")
            .insert(
                {
                    "workspace_id": workspace_id,
                    "type": "upload",
                    "status": "uploaded",
                    "original_filename": original_name,
                    "mime_type": detected_mime,
                    "file_size_bytes": file_size_bytes,
                    "file_hash": file_hash,
                    "uploaded_by": user_id,
                }
            )
            .execute()
        )
    except Exception as exc:
        if _is_duplicate_file_error(exc):
            existing = (
                db.table("sources")
                .select("id, status")
                .eq("workspace_id", workspace_id)
                .eq("file_hash", file_hash)
                .is_("deleted_at", "null")
                .maybe_single()
                .execute()
            )
            existing_data = _row(getattr(existing, "data", None))
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_file",
                    "existing_source_id": existing_data.get("id") if existing_data else None,
                    "existing_status": existing_data.get("status") if existing_data else None,
                },
            ) from exc
        raise
    rows = _rows(source_result.data)
    if not rows:
        raise HTTPException(status_code=500, detail="source_create_failed")
    return rows[0]


def _is_duplicate_file_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "uq_sources_workspace_file_hash_active" in text
        or "duplicate key value" in text
        or "23505" in text
    )


def _source_response(row: dict[str, Any]) -> SourceResponse:
    return SourceResponse(
        id=row["id"],
        workspace_id=row["workspace_id"],
        status=row["status"],
        title=row.get("title"),
        original_filename=row.get("original_filename"),
        mime_type=row.get("mime_type"),
        file_size_bytes=row.get("file_size_bytes"),
        created_at=_parse_datetime(row["created_at"]),
    )


def _optional_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


def _parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _rollback_upload(
    db: Client,
    source_id: str,
    storage_path: str,
    storage_uploaded: bool,
) -> None:
    if storage_uploaded:
        try:
            delete_from_storage(storage_path)
        except Exception:
            pass
    db.table("sources").update(
        {"status": "failed", "deleted_at": datetime.now(UTC).isoformat()}
    ).eq("id", source_id).execute()
