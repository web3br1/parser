from __future__ import annotations

from typing import Any

from worker_sync import db
from worker_sync.logging import logger


def reenqueue_queued_jobs(*, older_than_minutes: int = 5) -> dict[str, int]:
    logger.info("reenqueue_started")
    jobs = db.get_queued_jobs_for_reenqueue(older_than_minutes=older_than_minutes)
    dispatched = 0
    skipped = 0
    for job in jobs:
        if _dispatch(job):
            dispatched += 1
        else:
            skipped += 1
    result = {"scanned": len(jobs), "dispatched": dispatched, "skipped": skipped}
    logger.info("reenqueue_finished", **result)
    return result


def _dispatch(job: dict[str, Any]) -> bool:
    job_type = job.get("job_type")
    metadata = job.get("metadata") or {}
    if job_type == "ingest":
        _enqueue_ingest_source(
            job_id=job["id"],
            source_id=job["source_id"],
            workspace_id=job["workspace_id"],
            storage_path=metadata["storage_path"],
            declared_mime=metadata["declared_mime"],
            file_hash=metadata["file_hash"],
            request_id=metadata.get("request_id"),
        )
        return True

    if job_type == "classification":
        from worker_classification.tasks import classify_chunk_task

        classify_chunk_task.delay(
            job_id=job["id"],
            chunk_id=job["chunk_id"],
            workspace_id=job["workspace_id"],
            source_id=job["source_id"],
        )
        return True

    if job_type == "extraction":
        from worker_classification.extraction_queue import dispatch_extraction_job

        dispatch_extraction_job(str(job["id"]))
        return True

    return False


def _enqueue_ingest_source(**kwargs: Any) -> None:
    from worker_ingest.tasks import ingest_source

    ingest_source.delay(**kwargs)
