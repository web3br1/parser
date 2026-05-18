from __future__ import annotations

import os
from hashlib import sha256
from typing import Any, cast

from worker_extraction.prompt import get_prompt_version as get_extraction_prompt_version

from supabase import create_client
from worker_classification import db


def _row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    return None


def enqueue_extraction_job(
    *,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,
    confidence: float,
    prompt_version: str,
    model_name: str,
    request_id: str | None = None,
) -> str:
    """
    Step 1 of the outbox pattern: creates a processing_job with status=queued in DB.
    Must be called INSIDE the classifier DB transaction.

    Step 2 (caller responsibility): after the transaction commits, call:
        dispatch_extraction_job(job_id)

    Returns the job_id for the caller to dispatch after commit.
    This is NOT a formal outbox pattern, it is enqueue-after-insert.
    If .delay() fails after insert, the job stays queued and can be
    re-enqueued by a periodic scheduler.
    """
    payload = build_extraction_job_payload(
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        fact_type=fact_type,
        destination=destination,
        confidence=confidence,
        prompt_version=prompt_version,
        model_name=model_name,
        request_id=request_id,
    )

    return db.insert_extraction_job(
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_id=chunk_id,
        idempotency_key=str(payload["idempotency_key"]),
        metadata=cast(dict[str, Any], payload["metadata"]),
    )


def build_extraction_job_payload(
    *,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,
    confidence: float,
    prompt_version: str,
    model_name: str,
    request_id: str | None = None,
) -> dict[str, object]:
    """Builds the queued extraction job payload for atomic classification RPCs."""
    extraction_model = os.getenv("EXTRACTION_MODEL", "gpt-4o")
    extraction_prompt_version = get_extraction_prompt_version(fact_type)
    idempotency_key = sha256(
        (
            f"extraction:{chunk_id}:{fact_type}:"
            f"{extraction_prompt_version}:{extraction_model}"
        ).encode()
    ).hexdigest()

    return {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "job_type": "extraction",
        "status": "queued",
        "idempotency_key": idempotency_key,
        "metadata": {
            "fact_type": fact_type,
            "destination": destination,
            "classification_confidence": confidence,
            "classification_prompt_version": prompt_version,
            "classification_model": model_name,
            "extraction_prompt_version": extraction_prompt_version,
            "extraction_model": extraction_model,
            "request_id": request_id,
        },
    }


def dispatch_extraction_job(job_id: str) -> None:
    """
    Step 2 of the outbox pattern: enqueues the extraction job on the Celery broker.
    Must be called AFTER the classifier DB transaction has committed successfully.

    If this call fails, the job remains queued in DB and will be retried by the
    periodic scheduler. The chunk is never left in an inconsistent state.
    """
    from worker_extraction.tasks import extract_fact  # late import avoids circular dep

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    job_result = (
        supabase.table("processing_jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
    )
    job = _row(job_result.data)
    if not job:
        return

    metadata = _row(job.get("metadata")) or {}
    extract_fact.delay(
        job_id=job_id,
        chunk_id=str(job["chunk_id"]),
        workspace_id=str(job["workspace_id"]),
        source_id=str(job["source_id"]),
        fact_type=str(metadata["fact_type"]),
        destination=str(metadata["destination"]),
        classification_confidence=float(metadata["classification_confidence"]),
        classification_prompt_version=str(metadata["classification_prompt_version"]),
        request_id=cast(str | None, metadata.get("request_id")),
    )
