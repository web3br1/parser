from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from worker_extraction.evidence import EvidenceSpanInput


@dataclass(frozen=True)
class Chunk:
    id: str
    workspace_id: str
    source_id: str
    status: str
    content: str
    metadata: dict  # type: ignore[type-arg]


@dataclass(frozen=True)
class Job:
    id: str
    status: str


def get_chunk(chunk_id: str) -> Chunk:
    result = (
        _client()
        .table("chunks")
        .select("id,workspace_id,source_id,status,content,metadata")
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
        metadata=dict(row.get("metadata") or {}),
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


def mark_job_failed(job_id: str, reason: str) -> None:
    _client().table("processing_jobs").update(
        {"status": "failed", "finished_at": _now(), "error_message": reason}
    ).eq("id", job_id).execute()


def mark_job_retrying(job_id: str) -> None:
    _client().table("processing_jobs").update({"status": "retrying"}).eq("id", job_id).execute()


def create_evidence_span(span_input: EvidenceSpanInput) -> str:
    """Creates an evidence_span record and returns its UUID."""
    raise NotImplementedError


def insert_extracted_fact(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    evidence_span_id: str | None,
    fact_type: str,
    schema_version: str,
    content: dict[str, Any],
    normalized_content: dict[str, Any],
    confidence: float,
    model_name: str,
    prompt_version: str,
) -> str:
    """Inserts into extracted_facts and returns the new UUID."""
    raise NotImplementedError


def insert_business_rule(
    *,
    workspace_id: str,
    source_id: str,
    chunk_id: str,
    evidence_span_id: str,      # NOT NULL per migration 010
    rule_type: str,
    schema_version: str,
    condition: dict[str, Any],
    action: dict[str, Any],
    confidence: float,
    model_name: str,
    prompt_version: str,
) -> str:
    """Inserts into business_rules and returns the new UUID."""
    raise NotImplementedError


def complete_extraction_job(
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    chunk_status: str,
    idempotency_key: str,
    unknown_item: dict[str, Any] | None,
    evidence_span: dict[str, Any] | None,
    fact_records: list[dict[str, Any]],
    rule_record: dict[str, Any] | None,
    grounding_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _client().rpc(
        "complete_extraction_job",
        {
            "target_job_id": job_id,
            "target_chunk_id": chunk_id,
            "target_workspace_id": workspace_id,
            "target_source_id": source_id,
            "new_chunk_status": chunk_status,
            "job_idempotency_key": idempotency_key,
            "unknown_item": unknown_item,
            "evidence_span": evidence_span,
            "fact_records": fact_records,
            "rule_record": rule_record,
            "grounding_result": grounding_result,
        },
    ).execute()
    return dict(result.data or {})


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
