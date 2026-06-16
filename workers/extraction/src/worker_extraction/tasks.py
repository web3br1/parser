from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, NoReturn

from celery import Task
from celery.exceptions import Retry

from worker_extraction import db
from worker_extraction import grounding as grnd
from worker_extraction.celery_app import (
    app,
    extraction_task_soft_time_limit,
    extraction_task_time_limit,
)
from worker_extraction.evidence import (
    EvidenceSpanInput,
    build_evidence_span_input,
    compute_quote_hash,
)
from worker_extraction.extractor import ExtractionOutput, extract
from worker_extraction.logging import logger
from worker_extraction.prompt import get_prompt_version


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _idempotency_key(
    *,
    chunk_id: str,
    fact_type: str,
    prompt_version: str,
    model_name: str,
) -> str:
    payload = f"extraction:{chunk_id}:{fact_type}:{prompt_version}:{model_name}"
    return sha256(payload.encode()).hexdigest()


@app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="worker_extraction.tasks.extract_fact",
    max_retries=2,
    default_retry_delay=20,
    acks_late=True,
    soft_time_limit=extraction_task_soft_time_limit(),
    time_limit=extraction_task_time_limit(),
)
def extract_fact(
    self: Task,
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,                       # "extracted_facts" | "business_rules"
    classification_confidence: float,
    classification_prompt_version: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    return _extract_fact_impl(
        self,
        job_id=job_id,
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        fact_type=fact_type,
        destination=destination,
        classification_confidence=classification_confidence,
        classification_prompt_version=classification_prompt_version,
        request_id=request_id,
    )


def _extract_fact_impl(
    self: Task,
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    fact_type: str,
    destination: str,
    classification_confidence: float,
    classification_prompt_version: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    prompt_version = get_prompt_version(fact_type)
    model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o")
    idempotency_key = _idempotency_key(
        chunk_id=chunk_id,
        fact_type=fact_type,
        prompt_version=prompt_version,
        model_name=model_name,
    )

    try:
        # 1. IDEMPOTENCY -------------------------------------------------------
        existing = db.get_job_by_idempotency_key(idempotency_key)
        if existing is not None and existing.status == "succeeded":
            return {"status": "succeeded", "cached": True}

        # 2. START -------------------------------------------------------------
        worker_id = getattr(getattr(self, "request", None), "id", None) or "extraction-worker"
        if not db.claim_job(job_id, worker_id=str(worker_id), idempotency_key=idempotency_key):
            logger.info("job_claim_skipped", job_id=job_id, chunk_id=chunk_id)
            return {"status": "skipped", "reason": "job_claim_failed"}

        logger.info(
            "extraction_started",
            job_id=job_id,
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            source_id=source_id,
            workflow_id=source_id,
            fact_type=fact_type,
            request_id=request_id,
        )
        chunk = db.get_chunk(chunk_id)

        if chunk.workspace_id != workspace_id:
            db.mark_job_failed(job_id, reason="workspace_mismatch")
            logger.error(
                "extraction_failed",
                chunk_id=chunk_id,
                reason="workspace_mismatch",
            )
            return {"status": "failed", "reason": "workspace_mismatch"}

        # 3. FIRST EXTRACTION ATTEMPT ------------------------------------------
        output = extract(chunk.content, fact_type, retry=False)

        # 4. INTERNAL RETRY (parse/validation failure on first attempt) --------
        if output.status in ("parse_failed", "validation_failed"):
            request_retries = int(
                getattr(getattr(self, "request", None), "retries", 0) or 0
            )
            if request_retries == 0:
                logger.warning(
                    "extraction_retry",
                    chunk_id=chunk_id,
                    fact_type=fact_type,
                    reason=output.status,
                )
                output = extract(chunk.content, fact_type, retry=True)

        # 5. TOKEN LOGGING (always, even on domain failure) -------------------
        db.log_token_usage(
            workspace_id=workspace_id,
            source_id=source_id,
            chunk_id=chunk_id,
            operation="extract",
            model=output.model_name,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
            provider=output.model_provider,
            prompt_version=output.prompt_version,
            estimated_cost_usd=output.estimated_cost_usd,
            latency_ms=output.latency_ms,
            job_id=job_id,
        )

        # 6. DOMAIN FAILURE AFTER RETRY ----------------------------------------
        if output.status in ("failed", "parse_failed", "validation_failed"):
            complete_result = _complete_unknown(
                job_id=job_id,
                chunk_id=chunk_id,
                workspace_id=workspace_id,
                source_id=source_id,
                idempotency_key=idempotency_key,
                raw_text=chunk.content[:2000],
                suggested_fact_type=fact_type,
                confidence=classification_confidence,
                metadata={
                    "reason": output.status,
                    "fact_type": fact_type,
                    "validation_errors": output.validation_errors[:5],
                },
            )
            source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)
            return {
                "status": "succeeded",
                "chunk_status": "needs_review",
                "reason": output.status,
                "fact_type": fact_type,
                "source_status": source_status,
                "records_created": complete_result.get("records_created", 0),
            }

        # 7. CONTACT_INFO ALL-NULL GUARD ---------------------------------------
        if fact_type == "contact_info" and _contact_info_is_empty(output.validated_data):
            complete_result = _complete_unknown(
                job_id=job_id,
                chunk_id=chunk_id,
                workspace_id=workspace_id,
                source_id=source_id,
                idempotency_key=idempotency_key,
                raw_text=chunk.content[:2000],
                suggested_fact_type=fact_type,
                confidence=classification_confidence,
                metadata={"reason": "empty_contact_info"},
            )
            source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)
            return {
                "status": "succeeded",
                "chunk_status": "needs_review",
                "reason": "empty_contact_info",
                "fact_type": fact_type,
                "source_status": source_status,
                "records_created": complete_result.get("records_created", 0),
            }

        # 8. EVIDENCE SPAN -----------------------------------------------------
        span_input = build_evidence_span_input(
            workspace_id=workspace_id,
            source_id=source_id,
            chunk_id=chunk_id,
            llm_evidence={
                "quote": output.evidence_quote,
                "char_start": output.evidence_char_start,
                "char_end": output.evidence_char_end,
            },
            chunk_metadata=chunk.metadata,
        )

        if destination == "business_rules" and span_input is None:
            # evidence_span is NOT NULL in migration 010 — domain failure
            complete_result = _complete_unknown(
                job_id=job_id,
                chunk_id=chunk_id,
                workspace_id=workspace_id,
                source_id=source_id,
                idempotency_key=idempotency_key,
                raw_text=chunk.content[:2000],
                suggested_fact_type=fact_type,
                confidence=classification_confidence,
                metadata={"reason": "missing_evidence_quote"},
            )
            source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)
            return {
                "status": "succeeded",
                "chunk_status": "needs_review",
                "reason": "missing_evidence_quote",
                "source_status": source_status,
                "records_created": complete_result.get("records_created", 0),
            }

        # 8.5 GROUNDING (Truth Contract gate, flag-gated, warn-only) ----------
        # parse_artifact_created -> truth_evaluated. Default OFF preserves prior
        # behavior. Only required-grounding types can route a record to review.
        grounding_payload: dict[str, Any] | None = None
        if grnd.grounding_enabled():
            grounding_result = grnd.evaluate_for_extraction(
                output=output,
                fact_type=fact_type,
                destination=destination,
                chunk_text=chunk.content,
                span_input=span_input,
            )
            grounding_payload = grnd.to_payload(grounding_result)
            if grnd.blocks_record(grounding_result):
                complete_result = _complete_unknown(
                    job_id=job_id,
                    chunk_id=chunk_id,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    idempotency_key=idempotency_key,
                    raw_text=chunk.content[:2000],
                    suggested_fact_type=fact_type,
                    confidence=classification_confidence,
                    metadata={
                        "reason": grounding_result.grounding_reason,
                        "fact_type": fact_type,
                        "grounding_status": grounding_result.grounding_status,
                    },
                    grounding_result=grounding_payload,
                )
                source_status = _finalize_source_state(
                    source_id=source_id, workspace_id=workspace_id
                )
                logger.info(
                    "grounding_routed_to_review",
                    chunk_id=chunk_id,
                    fact_type=fact_type,
                    reason=grounding_result.grounding_reason,
                )
                return {
                    "status": "succeeded",
                    "chunk_status": "needs_review",
                    "reason": grounding_result.grounding_reason,
                    "fact_type": fact_type,
                    "source_status": source_status,
                    "records_created": complete_result.get("records_created", 0),
                }

        # 9. PERSIST (atomic RPC) ---------------------------------------------
        complete_result = _complete_success(
            job_id=job_id,
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            source_id=source_id,
            idempotency_key=idempotency_key,
            fact_type=fact_type,
            destination=destination,
            classification_confidence=classification_confidence,
            chunk_text=chunk.content,
            output=output,
            evidence_span=_evidence_payload(span_input),
            grounding_result=grounding_payload,
        )
        records_created = int(complete_result.get("records_created", 0))
        source_status = _finalize_source_state(source_id=source_id, workspace_id=workspace_id)

        # 10. RETURN -----------------------------------------------------------
        if records_created == 0:
            return {
                "status": "succeeded",
                "chunk_status": "needs_review",
                "reason": "no_records_created",
                "fact_type": fact_type,
                "records_created": 0,
                "source_status": source_status,
            }

        logger.info(
            "extraction_succeeded",
            chunk_id=chunk_id,
            fact_type=fact_type,
            records_created=records_created,
        )
        return {
            "status": "succeeded",
            "chunk_id": chunk_id,
            "chunk_status": "extracted",
            "fact_type": fact_type,
            "records_created": records_created,
            "input_tokens": output.input_tokens,
            "output_tokens": output.output_tokens,
            "source_status": source_status,
        }

    except Retry:
        raise
    except Exception as exc:
        return _handle_technical_failure(
            self, job_id, chunk_id, fact_type, exc,
            source_id=source_id, workspace_id=workspace_id,
        )


def _complete_unknown(
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    idempotency_key: str,
    raw_text: str,
    suggested_fact_type: str | None,
    confidence: float,
    metadata: dict[str, Any],
    grounding_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return db.complete_extraction_job(
        job_id=job_id,
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_status="needs_review",
        idempotency_key=idempotency_key,
        unknown_item={
            "raw_text": raw_text,
            "suggested_fact_type": suggested_fact_type,
            "confidence": confidence,
            "metadata": metadata,
        },
        evidence_span=None,
        fact_records=[],
        rule_record=None,
        grounding_result=grounding_result,
    )


def _complete_success(
    *,
    job_id: str,
    chunk_id: str,
    workspace_id: str,
    source_id: str,
    idempotency_key: str,
    fact_type: str,
    destination: str,
    classification_confidence: float,
    chunk_text: str,
    output: ExtractionOutput,
    evidence_span: dict[str, Any] | None,
    grounding_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fact_records: list[dict[str, Any]] = []
    rule_record: dict[str, Any] | None = None

    if output.is_multi:
        for record in output.records:
            fact_records.append(
                _fact_record(
                    fact_type=fact_type,
                    content=record,
                    normalized_content=record,
                    confidence=classification_confidence,
                    output=output,
                )
            )
    elif destination == "business_rules":
        rule_record = {
            "rule_type": fact_type,
            "schema_version": "1.0.0",
            "condition": output.validated_data.get("condition") or {},
            "action": output.validated_data.get("action") or {},
            "confidence": classification_confidence,
            "model_name": output.model_name,
            "prompt_version": output.prompt_version,
        }
    else:
        fact_records.append(
            _fact_record(
                fact_type=fact_type,
                content=output.raw_data,
                normalized_content=output.normalized_content,
                confidence=classification_confidence,
                output=output,
            )
        )

    unknown_item = None
    chunk_status = "extracted"
    if not fact_records and rule_record is None:
        chunk_status = "needs_review"
        unknown_item = {
            "raw_text": chunk_text[:2000],
            "suggested_fact_type": fact_type,
            "confidence": classification_confidence,
            "metadata": {"reason": "no_records_created", "fact_type": fact_type},
        }

    return db.complete_extraction_job(
        job_id=job_id,
        chunk_id=chunk_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_status=chunk_status,
        idempotency_key=idempotency_key,
        unknown_item=unknown_item,
        evidence_span=evidence_span,
        fact_records=fact_records,
        rule_record=rule_record,
        grounding_result=grounding_result,
    )


def _fact_record(
    *,
    fact_type: str,
    content: dict[str, Any],
    normalized_content: dict[str, Any],
    confidence: float,
    output: ExtractionOutput,
) -> dict[str, Any]:
    return {
        "fact_type": fact_type,
        "schema_version": "1.0.0",
        "content": content,
        "normalized_content": normalized_content,
        "confidence": confidence,
        "model_name": output.model_name,
        "prompt_version": output.prompt_version,
    }


def _evidence_payload(span_input: EvidenceSpanInput | None) -> dict[str, Any] | None:
    if span_input is None:
        return None
    quote = span_input.quote
    return {
        "quote": quote,
        "quote_hash": compute_quote_hash(quote),
        "char_start": span_input.char_start,
        "char_end": span_input.char_end,
        "page_number": span_input.page_number,
        "sheet_name": span_input.sheet_name,
        "row_number": span_input.row_number,
    }


def _contact_info_is_empty(validated_data: dict) -> bool:  # type: ignore[type-arg]
    """True if all ContactInfo fields are None, absent, empty, or whitespace."""
    fields = ("phone", "email", "address", "website", "whatsapp", "contact_name")
    return all(_is_blank_contact_value(validated_data.get(field)) for field in fields)


def _is_blank_contact_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _handle_technical_failure(
    self: Task,
    job_id: str,
    chunk_id: str,
    fact_type: str,
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
        raise self.retry(exc=exc, countdown=20)

    max_retries = int(getattr(self, "max_retries", 0) or 0)
    retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
    if retries >= max_retries:
        db.mark_job_failed(job_id, reason=error_name)
        logger.error(
            "extraction_failed_final",
            chunk_id=chunk_id,
            fact_type=fact_type,
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
