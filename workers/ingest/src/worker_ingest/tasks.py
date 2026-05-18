from hashlib import sha256
from pathlib import Path
from typing import Any

from celery import Task
from celery.exceptions import Retry
from parsers import get_parser
from parsers.chunker import chunk_extraction
from parsers.quality_gate import run_quality_gate
from security.file_validator import validate_file

from worker_ingest import db
from worker_ingest.celery_app import app
from worker_ingest.logging import logger
from worker_ingest.storage import download_from_storage

DOMAIN_FAILURES: set[str] = {
    "pages_exceeded",
    "rows_exceeded",
    "mime_mismatch",
    "magic_bytes_fail",
    "too_short",
    "all_pages_empty",
    "no_chunks_generated",
    "empty_file",
    "size_exceeded",
    "extension_blocked",
    "parse_failed",
    "unsupported_format",
    "workspace_mismatch",
}


def is_domain_failure(reason: str) -> bool:
    return reason in DOMAIN_FAILURES


@app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="worker_ingest.tasks.ingest_source",
    max_retries=1,
    default_retry_delay=10,
    acks_late=True,
    soft_time_limit=300,
    time_limit=360,
)
def ingest_source(
    self: Task,
    *,
    job_id: str,
    source_id: str,
    workspace_id: str,
    storage_path: str,
    declared_mime: str,
    file_hash: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    local_path: str | None = None
    try:
        job = db.get_job(job_id)
        if job.status in {"succeeded", "failed"}:
            return {"status": job.status, "cached": True}

        idempotency_key = sha256(f"ingest:{source_id}:{file_hash}".encode()).hexdigest()
        existing = db.get_job_by_idempotency_key(idempotency_key)
        if existing is not None and existing.id != job_id and existing.status == "succeeded":
            return {"status": "succeeded", "cached": True, "original_job_id": existing.id}

        worker_id = getattr(getattr(self, "request", None), "id", None) or "ingest-worker"
        if not db.claim_job(job_id, worker_id=str(worker_id), idempotency_key=idempotency_key):
            logger.info("job_claim_skipped", job_id=job_id, source_id=source_id)
            return {"status": "skipped", "reason": "job_claim_failed"}

        logger.info(
            "ingest_started",
            job_id=job_id,
            source_id=source_id,
            workspace_id=workspace_id,
            workflow_id=source_id,
            request_id=request_id,
        )

        local_path = download_from_storage(storage_path)
        path = Path(local_path)

        validation = validate_file(path, declared_mime)
        if not validation.valid:
            reason = validation.reason.value if validation.reason else "invalid_file"
            return _fail_domain(job_id, source_id, reason)

        logger.info(
            "file_validated",
            job_id=job_id,
            source_id=source_id,
            file_size_bytes=validation.file_size_bytes,
        )

        source = db.get_source(source_id)
        if source.workspace_id != workspace_id:
            return _fail_domain(job_id, source_id, "workspace_mismatch")

        parser = get_parser(declared_mime)
        extraction = parser.extract(path)
        logger.info(
            "extraction_done",
            job_id=job_id,
            source_id=source_id,
            total_chars=extraction.total_chars,
            total_pages=len(extraction.pages),
        )

        if extraction.error is not None:
            reason = extraction.error.value
            if is_domain_failure(reason):
                return _fail_domain(job_id, source_id, reason)
            return _retry(self, job_id, source_id, reason, RuntimeError(reason))

        report = run_quality_gate(extraction)
        if not report.passed:
            return _fail_domain(job_id, source_id, report.rejection_reason or "quality_failed")

        logger.info("quality_passed", job_id=job_id, source_id=source_id, warnings=report.warnings)

        chunks = chunk_extraction(extraction)
        if len(chunks) == 0:
            return _fail_domain(job_id, source_id, "no_chunks_generated")

        try:
            db.complete_ingest_job(
                job_id=job_id,
                source_id=source_id,
                workspace_id=workspace_id,
                report=report,
                chunks=chunks,
            )
        except Retry:
            raise
        except Exception as exc:
            return _retry(self, job_id, source_id, "db_transaction_failed", exc)

        logger.info("chunks_stored", job_id=job_id, source_id=source_id, chunks_created=len(chunks))

        try:
            dispatched = db.dispatch_classification_jobs(
                source_id=source_id,
                workspace_id=workspace_id,
                request_id=request_id,
            )
            logger.info(
                "classification_dispatched",
                job_id=job_id,
                source_id=source_id,
                chunks_dispatched=len(dispatched),
            )
        except Exception as exc:
            # Log but do not fail ingest — sync worker will re-enqueue on next run.
            logger.warning(
                "classification_dispatch_failed",
                job_id=job_id,
                source_id=source_id,
                error_type=type(exc).__name__,
            )
        logger.info(
            "ingest_succeeded", job_id=job_id, source_id=source_id, chunks_created=len(chunks)
        )
        return {
            "status": "succeeded",
            "chunks_created": len(chunks),
            "total_chars": report.total_chars,
            "warnings": report.warnings,
        }
    except Retry:
        raise
    except Exception as exc:
        reason = exc.__class__.__name__
        if is_domain_failure(reason):
            return _fail_domain(job_id, source_id, reason)
        return _retry(self, job_id, source_id, reason, exc)
    finally:
        if local_path is not None:
            try:
                Path(local_path).unlink(missing_ok=True)
                logger.info(
                    "temp_file_deleted",
                    job_id=job_id,
                    source_id=source_id,
                    workspace_id=workspace_id,
                )
            except Exception as exc:
                logger.warning(
                    "temp_file_cleanup_failed",
                    job_id=job_id,
                    source_id=source_id,
                    workspace_id=workspace_id,
                    error_type=type(exc).__name__,
                )


def _fail_domain(job_id: str, source_id: str, reason: str) -> dict[str, Any]:
    db.update_source(source_id, status="failed")
    db.update_job(job_id, status="failed", error=reason, finished_at=db.utc_now())
    logger.error("ingest_failed", job_id=job_id, source_id=source_id, reason=reason, retry=False)
    return {"status": "failed", "reason": reason}


def _retry(self: Task, job_id: str, source_id: str, reason: str, exc: Exception) -> dict[str, Any]:
    max_retries = int(getattr(self, "max_retries", 0) or 0)
    retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
    if retries >= max_retries:
        return _fail_domain(job_id, source_id, reason)

    db.update_job(job_id, status="retrying")
    logger.error("ingest_failed", job_id=job_id, source_id=source_id, reason=reason, retry=True)
    raise self.retry(exc=exc)
