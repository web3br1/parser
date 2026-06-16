import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from parsers.chunker import RawChunk
from parsers.quality_gate import QualityReport


@dataclass(frozen=True)
class JobRecord:
    id: str
    status: str


@dataclass(frozen=True)
class SourceRecord:
    id: str
    workspace_id: str


def get_job(job_id: str) -> JobRecord:
    result = (
        _client()
        .table("processing_jobs")
        .select("id,status")
        .eq("id", job_id)
        .single()
        .execute()
    )
    return JobRecord(id=str(result.data["id"]), status=str(result.data["status"]))


def get_job_by_idempotency_key(idempotency_key: str) -> JobRecord | None:
    result = (
        _client()
        .table("processing_jobs")
        .select("id,status")
        .eq("idempotency_key", idempotency_key)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return JobRecord(id=str(result.data["id"]), status=str(result.data["status"]))


def get_source(source_id: str) -> SourceRecord:
    result = (
        _client()
        .table("sources")
        .select("id,workspace_id")
        .eq("id", source_id)
        .single()
        .execute()
    )
    return SourceRecord(id=str(result.data["id"]), workspace_id=str(result.data["workspace_id"]))


def update_job(job_id: str, **fields: Any) -> None:
    payload = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in fields.items()
    }
    if "error" in payload:
        payload["error_message"] = payload.pop("error")
    chunks_created = payload.pop("chunks_created", None)
    if chunks_created is not None:
        payload["metadata"] = {"chunks_created": chunks_created}
    _client().table("processing_jobs").update(payload).eq("id", job_id).execute()


def claim_job(job_id: str, *, worker_id: str, idempotency_key: str) -> bool:
    result = (
        _client()
        .table("processing_jobs")
        .update(
            {
                "status": "running",
                "started_at": utc_now().isoformat(),
                "worker_id": worker_id,
                "idempotency_key": idempotency_key,
                "error_code": None,
                "error_message": None,
            }
        )
        .eq("id", job_id)
        .in_("status", ["queued", "retrying"])
        .execute()
    )
    data = getattr(result, "data", None)
    return bool(data) if data is not None else True


def update_source(source_id: str, **fields: Any) -> None:
    _client().table("sources").update(dict(fields)).eq("id", source_id).execute()


def upsert_quality_report(source_id: str, workspace_id: str, report: QualityReport) -> None:
    raise NotImplementedError


def delete_chunks_by_source(source_id: str) -> None:
    raise NotImplementedError


def insert_chunks(source_id: str, workspace_id: str, chunks: list[RawChunk]) -> None:
    raise NotImplementedError


def complete_ingest_job(
    *,
    job_id: str,
    source_id: str,
    workspace_id: str,
    report: QualityReport,
    chunks: list[RawChunk],
) -> None:
    _client().rpc(
        "complete_ingest_job",
        {
            "target_job_id": job_id,
            "target_source_id": source_id,
            "target_workspace_id": workspace_id,
            "quality_report": _quality_report_payload(report),
            "chunk_items": [_chunk_payload(chunk) for chunk in chunks],
        },
    ).execute()


def dispatch_classification_jobs(
    *,
    source_id: str,
    workspace_id: str,
    request_id: str | None = None,
) -> list[str]:
    """Query pending chunks for source and create + enqueue classification jobs.

    Uses send_task (string-based) to avoid importing the classification package.
    Safe to call even if some jobs already exist — get_or_create_processing_job
    is idempotent via the idempotency_key unique constraint.
    """
    from hashlib import sha256

    from worker_ingest.celery_app import app

    client = _client()

    result = (
        client.table("chunks")
        .select("id")
        .eq("source_id", source_id)
        .eq("workspace_id", workspace_id)
        .eq("status", "pending")
        .execute()
    )
    chunk_ids = [str(row["id"]) for row in (result.data or [])]

    job_ids: list[str] = []
    for chunk_id in chunk_ids:
        idempotency_key = sha256(f"classification:{chunk_id}".encode()).hexdigest()
        job_result = client.rpc(
            "get_or_create_processing_job",
            {
                "target_workspace_id": workspace_id,
                "target_source_id": source_id,
                "target_chunk_id": chunk_id,
                "target_job_type": "classification",
                "target_idempotency_key": idempotency_key,
                "job_metadata": {"request_id": request_id},
            },
        ).execute()
        job_id = str(job_result.data)
        job_ids.append(job_id)

        kwargs = {
            "chunk_id": chunk_id,
            "workspace_id": workspace_id,
            "source_id": source_id,
            "job_id": job_id,
            "request_id": request_id,
        }
        if os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1":
            from worker_classification.tasks import classify_chunk_task

            classify_chunk_task.delay(**kwargs)
        else:
            app.send_task(
                "worker_classification.tasks.classify_chunk_task",
                kwargs=kwargs,
                queue="classification",
            )

    return job_ids


@contextmanager
def transaction() -> Iterator[None]:
    yield


def utc_now() -> datetime:
    return datetime.now(UTC)


def _client() -> Any:
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _quality_report_payload(report: QualityReport) -> dict[str, Any]:
    return {
        "total_chars": report.total_chars,
        "total_pages": report.total_pages,
        "total_sheets": report.total_sheets,
        "empty_pages": report.empty_pages,
        "rejection_reason": report.rejection_reason,
        "warnings": report.warnings,
        "passed": report.passed,
    }


def _chunk_payload(chunk: RawChunk) -> dict[str, Any]:
    return {
        "chunk_index": chunk.chunk_index,
        "content": chunk.text,
        "content_hash": chunk.chunk_hash,
        "page_start": chunk.page_start or chunk.source_page,
        "page_end": chunk.page_end or chunk.source_page,
        "sheet_name": chunk.sheet_name,
        "row_start": chunk.row_start,
        "row_end": chunk.row_end,
        "section_title": chunk.section_heading,
        "token_count": chunk.token_estimate,
        "metadata": _chunk_metadata_payload(chunk),
    }


def _chunk_metadata_payload(chunk: RawChunk) -> dict[str, Any]:
    metadata = dict(chunk.metadata)
    if chunk.page_start is not None:
        metadata["page_start"] = chunk.page_start
    if chunk.page_end is not None:
        metadata["page_end"] = chunk.page_end
    if chunk.section_path is not None:
        metadata["section_path"] = chunk.section_path
    if chunk.section_title is not None:
        metadata["section_title"] = chunk.section_title
    if chunk.chunk_kind is not None:
        metadata["chunk_kind"] = chunk.chunk_kind
    if chunk.structure_risk_codes:
        metadata["structure_risk_codes"] = list(chunk.structure_risk_codes)
    return metadata
