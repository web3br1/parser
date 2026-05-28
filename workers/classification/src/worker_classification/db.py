import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Chunk:
    id: str
    workspace_id: str
    source_id: str
    status: str
    content: str


@dataclass(frozen=True)
class Job:
    id: str
    status: str


def get_chunk(chunk_id: str) -> Chunk:
    result = (
        _client()
        .table("chunks")
        .select("id,workspace_id,source_id,status,content")
        .eq("id", chunk_id)
        .single()
        .execute()
    )
    row = result.data
    return Chunk(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        source_id=str(row["source_id"]),
        status=str(row["status"]),
        content=str(row["content"]),
    )


def update_chunk_classification(chunk_id: str, classification: dict[str, Any]) -> None:
    (
        _client()
        .table("chunks")
        .update({"classification": classification})
        .eq("id", chunk_id)
        .execute()
    )


def update_chunk_status(chunk_id: str, status: str) -> None:
    _client().table("chunks").update({"status": status}).eq("id", chunk_id).execute()


def insert_unknown_queue_item(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    raw_text: str,
    suggested_fact_type: str | None,
    confidence: float,
    metadata: dict[str, Any],
) -> None:
    _client().table("unknown_facts_queue").insert(
        {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "raw_text": raw_text,
            "suggested_fact_type": suggested_fact_type,
            "confidence": confidence,
            "metadata": metadata,
        }
    ).execute()


def log_token_usage(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    provider: str = "unknown",
    prompt_version: str | None = None,
    estimated_cost_usd: float = 0.0,
    latency_ms: int = 0,
    job_id: str | None = None,
) -> None:
    _client().table("token_usage_log").insert(
        {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "chunk_id": chunk_id,
            "job_id": job_id,
            "provider": provider,
            "model": model,
            "operation": operation,
            "prompt_version": prompt_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost_usd,
            "latency_ms": latency_ms,
        }
    ).execute()


def get_job_by_idempotency_key(key: str) -> Job | None:
    result = (
        _client()
        .table("processing_jobs")
        .select("id,status")
        .eq("idempotency_key", key)
        .maybe_single()
        .execute()
    )
    data = getattr(result, "data", None)
    if not data:
        return None
    return Job(id=str(data["id"]), status=str(data["status"]))


def insert_extraction_job(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    idempotency_key: str,
    metadata: dict[str, Any],
) -> str:
    result = _client().rpc(
        "get_or_create_processing_job",
        {
            "target_workspace_id": workspace_id,
            "target_source_id": source_id,
            "target_chunk_id": chunk_id,
            "target_job_type": "extraction",
            "target_idempotency_key": idempotency_key,
            "job_metadata": metadata,
        },
    ).execute()
    return str(result.data)


def mark_job_running(job_id: str, idempotency_key: str) -> None:
    _client().table("processing_jobs").update(
        {
            "status": "running",
            "started_at": _now(),
            "idempotency_key": idempotency_key,
            "error_code": None,
            "error_message": None,
        }
    ).eq("id", job_id).execute()


def claim_job(job_id: str, *, worker_id: str, idempotency_key: str) -> bool:
    result = (
        _client()
        .table("processing_jobs")
        .update(
            {
                "status": "running",
                "started_at": _now(),
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


def mark_job_succeeded(job_id: str, idempotency_key: str) -> None:
    _client().table("processing_jobs").update(
        {
            "status": "succeeded",
            "finished_at": _now(),
            "idempotency_key": idempotency_key,
            "error_code": None,
            "error_message": None,
        }
    ).eq("id", job_id).execute()


def mark_job_succeeded_cached(job_id: str) -> None:
    _client().table("processing_jobs").update(
        {
            "status": "succeeded",
            "finished_at": _now(),
            "error_code": None,
            "error_message": None,
        }
    ).eq("id", job_id).execute()


def mark_job_failed(job_id: str, reason: str) -> None:
    _client().table("processing_jobs").update(
        {"status": "failed", "finished_at": _now(), "error_message": reason}
    ).eq("id", job_id).execute()


def mark_job_retrying(job_id: str) -> None:
    _client().table("processing_jobs").update({"status": "retrying"}).eq("id", job_id).execute()


def complete_classification_job(
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    classification: dict[str, Any],
    chunk_status: str,
    unknown_items: list[dict[str, Any]],
    extraction_jobs: list[dict[str, Any]],
    idempotency_key: str,
) -> list[str]:
    result = _client().rpc(
        "complete_classification_job",
        {
            "target_job_id": job_id,
            "target_chunk_id": chunk_id,
            "target_workspace_id": workspace_id,
            "target_source_id": source_id,
            "classification_payload": classification,
            "new_chunk_status": chunk_status,
            "unknown_items": unknown_items,
            "extraction_jobs": extraction_jobs,
            "job_idempotency_key": idempotency_key,
        },
    ).execute()
    return [str(job_id) for job_id in (result.data or [])]


def finalize_source_state(source_id: str, workspace_id: str) -> str | None:
    result = _client().rpc(
        "finalize_source_state_after_extraction",
        {
            "p_source_id": source_id,
            "p_workspace_id": workspace_id,
        },
    ).execute()
    return str(result.data) if result.data is not None else None


@contextmanager
def transaction() -> Iterator[None]:
    yield


def _client() -> Any:
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
