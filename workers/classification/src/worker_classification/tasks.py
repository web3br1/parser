import os
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, NoReturn

from celery import Task
from celery.exceptions import Retry

from worker_classification import db
from worker_classification.celery_app import app
from worker_classification.classifier import aggregate_chunk_status, classify_chunk
from worker_classification.extraction_queue import (
    build_extraction_job_payload,
    dispatch_extraction_job,
)
from worker_classification.logging import logger
from worker_classification.prompt import get_prompt_version


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _idempotency_key(
    *,
    chunk_id: str,
    prompt_version: str,
    model_provider: str,
    model_name: str,
) -> str:
    payload = f"{chunk_id}:{prompt_version}:{model_provider}:{model_name}"
    return sha256(payload.encode()).hexdigest()


@app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="worker_classification.tasks.classify_chunk_task",
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
    soft_time_limit=30,
    time_limit=45,
)
def classify_chunk_task(
    self: Task,
    *,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    job_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    return _classify_chunk_task_impl(
        self,
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        job_id=job_id,
        request_id=request_id,
    )


def _classify_chunk_task_impl(
    self: Task,
    *,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    job_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    prompt_version = get_prompt_version()
    model_provider = os.getenv("MODEL_PROVIDER", "openai")
    model_name = os.getenv("CLASSIFICATION_MODEL", "")
    idempotency_key = _idempotency_key(
        chunk_id=chunk_id,
        prompt_version=prompt_version,
        model_provider=model_provider,
        model_name=model_name,
    )

    try:
        existing = db.get_job_by_idempotency_key(idempotency_key)
        if existing is not None and existing.status == "succeeded":
            if existing.id != job_id:
                db.mark_job_succeeded_cached(job_id)
            return {"status": "succeeded", "cached": True}

        worker_id = getattr(getattr(self, "request", None), "id", None) or "classification-worker"
        if not db.claim_job(job_id, worker_id=str(worker_id), idempotency_key=idempotency_key):
            logger.info("job_claim_skipped", job_id=job_id, chunk_id=chunk_id)
            return {"status": "skipped", "reason": "job_claim_failed"}

        logger.info(
            "classification_started",
            job_id=job_id,
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            source_id=source_id,
            workflow_id=source_id,
            request_id=request_id,
        )

        chunk = db.get_chunk(chunk_id)
        if chunk.workspace_id != workspace_id:
            db.mark_job_failed(job_id, reason="workspace_mismatch")
            logger.error(
                "classification_failed",
                chunk_id=chunk_id,
                reason="workspace_mismatch",
            )
            return {"status": "failed", "reason": "workspace_mismatch"}

        if chunk.status not in {"pending", "needs_review"}:
            db.mark_job_succeeded(job_id, idempotency_key=idempotency_key)
            return {
                "status": "skipped",
                "job_status": "succeeded",
                "reason": f"chunk_status={chunk.status}",
            }

        try:
            result = classify_chunk(chunk.content)
        except ValueError as exc:
            if "classification_parse_failed" in str(exc):
                return _handle_parse_failure(
                    job_id=job_id,
                    chunk=chunk,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    prompt_version=prompt_version,
                    model_name=model_name,
                    idempotency_key=idempotency_key,
                )
            raise

        operation = (
            "classify_blocked_injection"
            if result.injection_check.injection_suspected
            else "classify"
        )
        db.log_token_usage(
            workspace_id=workspace_id,
            source_id=source_id,
            chunk_id=chunk_id,
            operation=operation,
            model=result.model_name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            provider=result.model_provider,
            prompt_version=result.prompt_version,
            estimated_cost_usd=result.estimated_cost_usd,
            latency_ms=result.latency_ms,
            job_id=job_id,
        )

        new_status = aggregate_chunk_status(result.decisions)
        classification_payload = {
            "decisions": [asdict(decision) for decision in result.decisions],
            "prompt_version": result.prompt_version,
            "model_name": result.model_name,
            "token_usage": {
                "input": result.input_tokens,
                "output": result.output_tokens,
                "estimated_cost_usd": result.estimated_cost_usd,
                "latency_ms": result.latency_ms,
            },
            "raw_response_hash": result.raw_response_hash,
            "classified_at": _now(),
            "injection_suspected": result.injection_check.injection_suspected,
        }
        unknown_items: list[dict[str, Any]] = []
        extraction_jobs: list[dict[str, Any]] = []
        for decision in result.decisions:
            if decision.destination == "unknown_facts_queue":
                unknown_items.append(
                    {
                        "raw_text": chunk.content[:2000],
                        "suggested_fact_type": (
                            decision.fact_type if decision.fact_type != "unknown" else None
                        ),
                        "confidence": decision.confidence,
                        "metadata": {
                            "chunk_id": chunk_id,
                            "reason": decision.reason,
                            "injection_patterns": result.injection_check.matched_patterns,
                        },
                    }
                )
            else:
                extraction_jobs.append(
                    build_extraction_job_payload(
                        chunk_id=chunk_id,
                        workspace_id=workspace_id,
                        source_id=source_id,
                        fact_type=decision.fact_type,
                        destination=decision.destination,
                        confidence=decision.confidence,
                        prompt_version=result.prompt_version,
                        model_name=result.model_name,
                        request_id=request_id,
                    )
                )

        pending_extraction_job_ids = db.complete_classification_job(
            job_id=job_id,
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            source_id=source_id,
            classification=classification_payload,
            chunk_status=new_status,
            unknown_items=unknown_items,
            extraction_jobs=extraction_jobs,
            idempotency_key=idempotency_key,
        )
        source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)

        dispatch_failures = 0
        for extraction_job_id in pending_extraction_job_ids:
            if not extraction_job_id:
                continue
            try:
                dispatch_extraction_job(extraction_job_id)
            except Exception as exc:
                dispatch_failures += 1
                logger.warning(
                    "extraction_dispatch_failed",
                    job_id=job_id,
                    extraction_job_id=extraction_job_id,
                    error_type=type(exc).__name__,
                )

        logger.info(
            "classification_succeeded",
            chunk_id=chunk_id,
            decisions=len(result.decisions),
            chunk_status=new_status,
            injection=result.injection_check.injection_suspected,
        )
        return {
            "status": "succeeded",
            "chunk_id": chunk_id,
            "chunk_status": new_status,
            "decisions": len(result.decisions),
            "injection_suspected": result.injection_check.injection_suspected,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "source_status": source_status,
            "dispatch_failures": dispatch_failures,
        }
    except Retry:
        raise
    except Exception as exc:
        return _handle_technical_failure(
            self, job_id, chunk_id, exc,
            source_id=source_id, workspace_id=workspace_id,
        )


def _handle_parse_failure(
    *,
    job_id: str,
    chunk: db.Chunk,
    workspace_id: str,
    source_id: str,
    prompt_version: str,
    model_name: str,
    idempotency_key: str,
) -> dict[str, Any]:
    db.complete_classification_job(
        job_id=job_id,
        chunk_id=chunk.id,
        workspace_id=workspace_id,
        source_id=source_id,
        classification={
            "decisions": [],
            "prompt_version": prompt_version,
            "model_name": model_name,
            "raw_response_hash": "",
            "classified_at": _now(),
            "reason": "classification_parse_failed",
        },
        chunk_status="needs_review",
        unknown_items=[
            {
                "raw_text": chunk.content[:2000],
                "suggested_fact_type": None,
                "confidence": 0.0,
                "metadata": {"reason": "classification_parse_failed"},
            }
        ],
        extraction_jobs=[],
        idempotency_key=idempotency_key,
    )
    source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)

    logger.warning("classification_parse_failed", chunk_id=chunk.id)
    return {
        "status": "succeeded",
        "chunk_status": "needs_review",
        "reason": "classification_parse_failed",
        "source_status": source_status,
    }


def _handle_technical_failure(
    self: Task,
    job_id: str,
    chunk_id: str,
    exc: Exception,
    *,
    source_id: str,
    workspace_id: str,
) -> NoReturn:
    error_name = type(exc).__name__
    if error_name == "RateLimitError":
        db.mark_job_retrying(job_id)
        raise self.retry(exc=exc, countdown=60)

    if error_name in {"APITimeoutError", "APIConnectionError"}:
        db.mark_job_retrying(job_id)
        raise self.retry(exc=exc, countdown=15)

    max_retries = int(getattr(self, "max_retries", 0) or 0)
    retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
    if retries >= max_retries:
        db.mark_job_failed(job_id, reason=error_name)
        logger.error(
            "classification_failed_final",
            chunk_id=chunk_id,
            error_type=error_name,
        )
        _finalize_source_state(source_id=source_id, workspace_id=workspace_id)
        raise exc
    else:
        db.mark_job_retrying(job_id)

    raise self.retry(exc=exc)


def _finalize_source_state(*, source_id: str, workspace_id: str) -> str | None:
    try:
        return db.finalize_source_state(source_id=source_id, workspace_id=workspace_id)
    except Exception as exc:
        logger.warning(
            "source_finalization_failed",
            source_id=source_id,
            workspace_id=workspace_id,
            error_type=type(exc).__name__,
        )
        return None
