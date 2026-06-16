from __future__ import annotations

from hashlib import sha256
from unittest.mock import MagicMock, patch

import pytest
from worker_extraction.extractor import ExtractionOutput
from worker_extraction.tasks import _contact_info_is_empty, extract_fact


class DummyTask:
    def __init__(self) -> None:
        self.retry_called = False
        self.request = MagicMock()
        self.request.retries = 0

    def retry(self, *, exc: Exception, countdown: int = 0) -> Exception:
        self.retry_called = True
        return exc


def _make_output(**kwargs) -> ExtractionOutput:  # type: ignore[no-untyped-def]
    defaults = dict(
        fact_type="service_price",
        status="ok",
        raw_data={
            "service_name": "Corte",
            "price_amount": 120.0,
            "currency": "BRL",
            "price_type": "fixed",
        },
        validated_data={
            "service_name": "Corte",
            "price_amount": 120.0,
            "currency": "BRL",
            "price_type": "fixed",
        },
        normalized_content={"service_name": "Corte", "price_amount": 120.0},
        evidence_quote="Corte R$120",
        evidence_char_start=None,
        evidence_char_end=None,
        ambiguities=[],
        model_name="gpt-4o",
        prompt_version="abc123",
        input_tokens=10,
        output_tokens=20,
        raw_response_hash="deadbeef",
        validation_errors=[],
        is_multi=False,
        records=[],
    )
    defaults.update(kwargs)
    return ExtractionOutput(**defaults)


def _make_chunk(
    workspace_id: str = "ws-1",
    status: str = "classified",
    content: str = "Corte feminino R$120",
) -> MagicMock:
    chunk = MagicMock()
    chunk.id = "chunk-1"
    chunk.workspace_id = workspace_id
    chunk.source_id = "src-1"
    chunk.status = status
    chunk.content = content
    chunk.metadata = {}
    return chunk


def _base_kwargs() -> dict:
    return dict(
        job_id="job-1",
        chunk_id="chunk-1",
        workspace_id="ws-1",
        source_id="src-1",
        fact_type="service_price",
        destination="extracted_facts",
        classification_confidence=0.92,
        classification_prompt_version="v1",
        request_id="req-123",
    )


# ---------------------------------------------------------------------------
# Grounding integration (Task 8) — flag-gated, warn-only
# ---------------------------------------------------------------------------


def _grounding_result(*, required: bool, status: str, reason: str) -> MagicMock:
    result = MagicMock()
    result.grounding_required = required
    result.grounding_status = status
    result.grounding_reason = reason
    return result


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
@patch("worker_extraction.tasks.grnd")
def test_grounding_disabled_passes_no_payload(
    mock_grnd: MagicMock,
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_grnd.grounding_enabled.return_value = False
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_build_span.return_value = MagicMock(quote="some quote")
    mock_db.complete_extraction_job.return_value = {"records_created": 1}
    mock_db.finalize_source_state.return_value = "extracted"
    mock_extract.return_value = _make_output()

    result = extract_fact.run.__func__(DummyTask(), **_base_kwargs())

    assert result["status"] == "succeeded"
    mock_grnd.evaluate_for_extraction.assert_not_called()
    assert mock_db.complete_extraction_job.call_args.kwargs["grounding_result"] is None


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
@patch("worker_extraction.tasks.grnd")
def test_grounding_required_failure_routes_to_review(
    mock_grnd: MagicMock,
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_grnd.grounding_enabled.return_value = True
    mock_grnd.evaluate_for_extraction.return_value = _grounding_result(
        required=True, status="failed", reason="grounding_evidence_not_literal"
    )
    mock_grnd.blocks_record.return_value = True
    mock_grnd.to_payload.return_value = {"grounding_status": "failed"}
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_build_span.return_value = MagicMock(quote="some quote")
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    mock_db.finalize_source_state.return_value = "needs_review"
    mock_extract.return_value = _make_output()

    result = extract_fact.run.__func__(DummyTask(), **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["chunk_status"] == "needs_review"
    assert result["reason"] == "grounding_evidence_not_literal"
    kwargs = mock_db.complete_extraction_job.call_args.kwargs
    # Required-grounding failure must not create a reliable record.
    assert kwargs["fact_records"] == []
    assert kwargs["rule_record"] is None
    assert kwargs["grounding_result"] == {"grounding_status": "failed"}


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
@patch("worker_extraction.tasks.grnd")
def test_grounding_warn_only_persists_fact_and_result(
    mock_grnd: MagicMock,
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_grnd.grounding_enabled.return_value = True
    mock_grnd.evaluate_for_extraction.return_value = _grounding_result(
        required=False, status="passed", reason="grounding_warn_only"
    )
    mock_grnd.blocks_record.return_value = False
    mock_grnd.to_payload.return_value = {"grounding_status": "passed"}
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_build_span.return_value = MagicMock(quote="some quote")
    mock_db.complete_extraction_job.return_value = {"records_created": 1}
    mock_db.finalize_source_state.return_value = "extracted"
    mock_extract.return_value = _make_output()

    result = extract_fact.run.__func__(DummyTask(), **_base_kwargs())

    assert result["records_created"] == 1
    kwargs = mock_db.complete_extraction_job.call_args.kwargs
    # Warn-only keeps the fact AND records the grounding result.
    assert len(kwargs["fact_records"]) == 1
    assert kwargs["grounding_result"] == {"grounding_status": "passed"}


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_idempotency_cached(mock_extract: MagicMock, mock_db: MagicMock) -> None:
    existing_job = MagicMock()
    existing_job.status = "succeeded"
    mock_db.get_job_by_idempotency_key.return_value = existing_job

    task = MagicMock()
    result = extract_fact.run.__func__(task, **_base_kwargs())

    assert result == {"status": "succeeded", "cached": True}
    mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# Workspace mismatch
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_workspace_mismatch(mock_extract: MagicMock, mock_db: MagicMock) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk(workspace_id="other-ws")

    task = MagicMock()
    result = extract_fact.run.__func__(task, **_base_kwargs())

    assert result["status"] == "failed"
    assert result["reason"] == "workspace_mismatch"
    mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
def test_success_extracted_fact(
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_build_span.return_value = MagicMock(quote="some quote")
    mock_db.complete_extraction_job.return_value = {"records_created": 1}
    mock_db.finalize_source_state.return_value = "extracted"
    mock_extract.return_value = _make_output()

    task = DummyTask()
    result = extract_fact.run.__func__(task, **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["records_created"] == 1
    assert result["source_status"] == "extracted"
    assert (
        result["chunk_status"] == "extracted"
        or "chunk_status" not in result
        or result.get("chunk_id") == "chunk-1"
    )
    mock_db.complete_extraction_job.assert_called_once()
    mock_db.finalize_source_state.assert_called_once_with(source_id="src-1", workspace_id="ws-1")
    assert len(mock_db.complete_extraction_job.call_args.kwargs["fact_records"]) == 1


# ---------------------------------------------------------------------------
# Domain failures → succeeded + needs_review
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_domain_failure_parse_failed_routes_to_unknown(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    # Both attempts fail
    mock_extract.return_value = _make_output(
        status="parse_failed",
        validated_data={},
        normalized_content={},
    )

    task = MagicMock()
    task.request.retries = 0
    result = extract_fact.run.__func__(task, **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["chunk_status"] == "needs_review"
    assert result["reason"] == "parse_failed"
    # self.retry must NOT be called for domain failures
    task.retry.assert_not_called()


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_parse_failed_retries_internally(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    """First call returns parse_failed; second (retry=True) also fails. Two calls total."""
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    mock_extract.return_value = _make_output(
        status="parse_failed",
        validated_data={},
        normalized_content={},
    )

    task = MagicMock()
    task.request.retries = 0
    extract_fact.run.__func__(task, **_base_kwargs())

    assert mock_extract.call_count == 2
    # Second call must use retry=True
    _, second_kwargs = mock_extract.call_args_list[1]
    assert second_kwargs.get("retry") is True


# ---------------------------------------------------------------------------
# business_rules: missing evidence quote → domain failure
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
def test_business_rule_missing_quote(
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    mock_extract.return_value = _make_output(
        fact_type="discount_rule",
        validated_data={"condition": {}, "action": {"discount_percentage": 10.0}},
        evidence_quote="",  # no quote
    )
    mock_build_span.return_value = None  # quote absent → None

    kwargs = _base_kwargs()
    kwargs.update(fact_type="discount_rule", destination="business_rules")
    task = MagicMock()
    result = extract_fact.run.__func__(task, **kwargs)

    assert result["status"] == "succeeded"
    assert result["reason"] == "missing_evidence_quote"
    assert mock_db.complete_extraction_job.call_args.kwargs["rule_record"] is None


# ---------------------------------------------------------------------------
# business_hours: multi-record
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.build_evidence_span_input")
@patch("worker_extraction.tasks.extract")
def test_business_hours_multi_creates_n_facts(
    mock_extract: MagicMock,
    mock_build_span: MagicMock,
    mock_db: MagicMock,
) -> None:
    records = [
        {"day_of_week": "mon", "open_time": "09:00", "close_time": "18:00", "is_closed": False},
        {"day_of_week": "tue", "open_time": "09:00", "close_time": "18:00", "is_closed": False},
        {"day_of_week": "sat", "open_time": "09:00", "close_time": "13:00", "is_closed": False},
    ]
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_build_span.return_value = MagicMock(quote="some quote")
    mock_db.complete_extraction_job.return_value = {"records_created": 3}
    mock_extract.return_value = _make_output(
        fact_type="business_hours",
        is_multi=True,
        records=records,
    )

    kwargs = _base_kwargs()
    kwargs.update(fact_type="business_hours", destination="extracted_facts")
    task = DummyTask()
    result = extract_fact.run.__func__(task, **kwargs)

    assert result["records_created"] == 3
    assert len(mock_db.complete_extraction_job.call_args.kwargs["fact_records"]) == 3


# ---------------------------------------------------------------------------
# contact_info all-null guard
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_contact_info_all_null_guard(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    mock_extract.return_value = _make_output(
        fact_type="contact_info",
        validated_data={
            "phone": None, "email": None, "address": None,
            "website": None, "whatsapp": None, "contact_name": None,
        },
    )

    kwargs = _base_kwargs()
    kwargs["fact_type"] = "contact_info"
    task = MagicMock()
    result = extract_fact.run.__func__(task, **kwargs)

    assert result["reason"] == "empty_contact_info"
    assert result["chunk_status"] == "needs_review"


# ---------------------------------------------------------------------------
# Idempotency key composition
# ---------------------------------------------------------------------------


def test_idempotency_key_includes_fact_type_and_model() -> None:
    from worker_extraction.tasks import _idempotency_key
    key1 = _idempotency_key(
        chunk_id="c1", fact_type="service_price", prompt_version="v1", model_name="gpt-4o"
    )
    key2 = _idempotency_key(
        chunk_id="c1", fact_type="discount_rule", prompt_version="v1", model_name="gpt-4o"
    )
    key3 = _idempotency_key(
        chunk_id="c1", fact_type="service_price", prompt_version="v1", model_name="gpt-3.5"
    )
    assert key1 != key2  # different fact_type
    assert key1 != key3  # different model
    assert key1 == sha256(b"extraction:c1:service_price:v1:gpt-4o").hexdigest()


# ---------------------------------------------------------------------------
# _contact_info_is_empty unit
# ---------------------------------------------------------------------------


def test_contact_info_is_empty_true() -> None:
    assert (
        _contact_info_is_empty(
            {
                "phone": None,
                "email": None,
                "address": None,
                "website": None,
                "whatsapp": None,
                "contact_name": None,
            }
        )
        is True
    )


def test_contact_info_is_empty_with_blank_strings() -> None:
    assert _contact_info_is_empty(
        {
            "phone": "",
            "email": "   ",
            "address": None,
            "website": "",
            "whatsapp": "\t",
            "contact_name": None,
        }
    ) is True


def test_contact_info_is_empty_false() -> None:
    assert _contact_info_is_empty({"phone": "(11) 9999"}) is False


# ---------------------------------------------------------------------------
# Token usage always logged
# ---------------------------------------------------------------------------


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_token_usage_logged_on_domain_failure(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    mock_db.complete_extraction_job.return_value = {"records_created": 0}
    mock_extract.return_value = _make_output(
        status="failed",
        validated_data={},
        normalized_content={},
    )

    task = MagicMock()
    task.request.retries = 1  # skip internal retry
    extract_fact.run.__func__(task, **_base_kwargs())

    mock_db.log_token_usage.assert_called_once()


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_final_technical_failure_marks_failed_and_finalizes_without_retry(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = True
    mock_db.get_chunk.return_value = _make_chunk()
    mock_extract.side_effect = RuntimeError("provider down")

    task = MagicMock()
    task.max_retries = 2
    task.request.retries = 2
    task.retry.side_effect = AssertionError("retry should not be called after permanent failure")

    with pytest.raises(RuntimeError):
        extract_fact.run.__func__(task, **_base_kwargs())

    mock_db.mark_job_failed.assert_called_once_with("job-1", reason="RuntimeError")
    mock_db.mark_job_retrying.assert_not_called()
    mock_db.finalize_source_state.assert_called_once_with(source_id="src-1", workspace_id="ws-1")
    task.retry.assert_not_called()


@patch("worker_extraction.tasks.db")
@patch("worker_extraction.tasks.extract")
def test_claim_failure_skips_without_extraction(
    mock_extract: MagicMock,
    mock_db: MagicMock,
) -> None:
    mock_db.get_job_by_idempotency_key.return_value = None
    mock_db.claim_job.return_value = False

    task = MagicMock()
    result = extract_fact.run.__func__(task, **_base_kwargs())

    assert result == {"status": "skipped", "reason": "job_claim_failed"}
    mock_db.get_chunk.assert_not_called()
    mock_extract.assert_not_called()
