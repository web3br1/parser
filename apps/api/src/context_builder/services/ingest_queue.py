from hashlib import sha256
from typing import Any

from observability.context import get_request_id
from observability.events import agent_event
from observability.logging import get_logger

from supabase import Client

AGENT = "api-agent"
STAGE = "ingest"
ACTION = "enqueue"


def create_and_enqueue_ingest_job(
    *,
    source_id: str,
    workspace_id: str,
    storage_path: str,
    declared_mime: str,
    file_hash: str,
    actor_user_id: str,
    db: Client,
) -> str:
    """
    Cria processing_job no DB e só depois enfileira o worker de ingestão.
    Se o enqueue falhar, o job permanece queued para re-enfileiramento.
    """
    idempotency_key = sha256(f"ingest:{source_id}:{file_hash}".encode()).hexdigest()
    request_id = get_request_id()

    job_result = db.rpc(
        "get_or_create_processing_job",
        {
            "target_workspace_id": workspace_id,
            "target_source_id": source_id,
            "target_chunk_id": None,
            "target_job_type": "ingest",
            "target_idempotency_key": idempotency_key,
            "job_metadata": {
                "storage_path": storage_path,
                "declared_mime": declared_mime,
                "file_hash": file_hash,
                "chunks_created": None,
                "request_id": request_id,
                "initiated_by_user_id": actor_user_id,
            },
        },
    ).execute()
    job_id = str(job_result.data)

    try:
        enqueue_ingest_source(
            job_id=job_id,
            source_id=source_id,
            workspace_id=workspace_id,
            storage_path=storage_path,
            declared_mime=declared_mime,
            file_hash=file_hash,
            request_id=request_id,
        )
        event, fields = agent_event(
            AGENT,
            STAGE,
            ACTION,
            "queued",
            request_id=request_id,
            workflow_id=source_id,
            job_id=job_id,
            workspace_id=workspace_id,
            source_id=source_id,
        )
        get_logger("api").info(
            event,
            **fields,
        )
    except Exception as exc:
        event, fields = agent_event(
            AGENT,
            STAGE,
            ACTION,
            "failed",
            request_id=request_id,
            workflow_id=source_id,
            job_id=job_id,
            workspace_id=workspace_id,
            source_id=source_id,
            error_type=type(exc).__name__,
            reason=str(exc),
        )
        get_logger("api").warning(
            event,
            **fields,
        )

    return job_id


def enqueue_ingest_source(**kwargs: Any) -> None:
    from worker_ingest.tasks import ingest_source

    ingest_source.delay(**kwargs)
