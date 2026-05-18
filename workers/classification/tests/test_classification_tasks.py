from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from security.injection_detector import InjectionCheckResult
from worker_classification import tasks
from worker_classification.classifier import (
    ChunkClassificationResult,
    ClassificationDecision,
)
from worker_classification.db import Chunk, Job


@dataclass
class FakeTask:
    retries: int = 0
    max_retries: int = 2

    def __post_init__(self) -> None:
        self.request = SimpleNamespace(retries=self.retries)

    def retry(self, exc: Exception, countdown: int | None = None) -> None:
        raise RetryCalled(exc, countdown)


class RetryCalled(Exception):
    def __init__(self, exc: Exception, countdown: int | None) -> None:
        super().__init__(str(exc))
        self.exc = exc
        self.countdown = countdown


class RecordingTransaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append("tx_enter")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.events.append("tx_exit")


def _call(fake_task: FakeTask, **kwargs: str) -> dict:
    return tasks._classify_chunk_task_impl(fake_task, **kwargs)


def _base_kwargs() -> dict[str, str]:
    return {
        "chunk_id": "chunk-1",
        "workspace_id": "workspace-1",
        "source_id": "source-1",
        "job_id": "job-1",
    }


def _result(
    decisions: list[ClassificationDecision],
    injection: bool = False,
    model_name: str = "test-model",
) -> ChunkClassificationResult:
    return ChunkClassificationResult(
        injection_check=InjectionCheckResult(
            injection_suspected=injection,
            matched_patterns=["pattern"] if injection else [],
        ),
        raw_response=None if injection else object(),  # type: ignore[arg-type]
        decisions=decisions,
        prompt_version="prompt-v1",
        model_name=model_name,
        model_provider="openai",
        input_tokens=0 if injection else 11,
        output_tokens=0 if injection else 5,
        raw_response_hash="" if injection else "hash-value",
    )


@contextmanager
def _transaction() -> Iterator[None]:
    yield


def _patch_common(monkeypatch, chunk: Chunk, events: list[str] | None = None) -> None:
    monkeypatch.setattr(tasks.db, "get_job_by_idempotency_key", lambda key: None)
    monkeypatch.setattr(tasks.db, "claim_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(tasks.db, "mark_job_running", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "mark_job_succeeded", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "mark_job_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "mark_job_retrying", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "get_chunk", lambda chunk_id: chunk)
    monkeypatch.setattr(tasks.db, "update_chunk_classification", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "update_chunk_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "insert_unknown_queue_item", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "log_token_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "complete_classification_job", lambda **kwargs: [])
    monkeypatch.setattr(tasks.db, "finalize_source_state", lambda **kwargs: "extracted")
    if events is None:
        monkeypatch.setattr(tasks.db, "transaction", _transaction)
    else:
        monkeypatch.setattr(tasks.db, "transaction", lambda: RecordingTransaction(events))


def test_succeeded_job_is_cached(monkeypatch) -> None:
    monkeypatch.setattr(
        tasks.db,
        "get_job_by_idempotency_key",
        lambda key: Job(id="job-old", status="succeeded"),
    )
    classify_called = False

    def classify(_content: str) -> None:
        nonlocal classify_called
        classify_called = True

    monkeypatch.setattr(tasks, "classify_chunk", classify)
    monkeypatch.setattr(tasks.db, "mark_job_succeeded_cached", lambda job_id: None)

    result = _call(FakeTask(), **_base_kwargs())

    assert result == {"status": "succeeded", "cached": True}
    assert classify_called is False


def test_new_job_for_cached_chunk_is_marked_succeeded(monkeypatch) -> None:
    monkeypatch.setattr(
        tasks.db,
        "get_job_by_idempotency_key",
        lambda key: Job(id="job-old", status="succeeded"),
    )
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tasks.db,
        "mark_job_succeeded_cached",
        lambda job_id: marked.append((job_id, "cached")),
    )
    monkeypatch.setattr(
        tasks.db,
        "claim_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not claim")),
    )
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: (_ for _ in ()).throw(AssertionError("should not classify")),
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result == {"status": "succeeded", "cached": True}
    assert len(marked) == 1
    assert marked[0] == ("job-1", "cached")


def test_workspace_mismatch_fails_without_llm(monkeypatch) -> None:
    _patch_common(
        monkeypatch,
        Chunk("chunk-1", "other-workspace", "source-1", "pending", "content"),
    )
    calls: list[str] = []
    monkeypatch.setattr(tasks.db, "mark_job_failed", lambda *args, **kwargs: calls.append("failed"))
    monkeypatch.setattr(tasks, "classify_chunk", lambda content: calls.append("llm"))

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "failed"
    assert result["reason"] == "workspace_mismatch"
    assert calls == ["failed"]


def test_already_classified_chunk_is_skipped(monkeypatch) -> None:
    _patch_common(
        monkeypatch,
        Chunk("chunk-1", "workspace-1", "source-1", "classified", "content"),
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "skipped"
    assert result["job_status"] == "succeeded"


def test_classification_parse_failed_succeeds_with_review(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "x" * 3000)
    _patch_common(monkeypatch, chunk)
    complete_payloads: list[dict] = []
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: (_ for _ in ()).throw(ValueError("classification_parse_failed: {bad")),
    )
    monkeypatch.setattr(
        tasks.db,
        "complete_classification_job",
        lambda **kwargs: complete_payloads.append(kwargs) or [],
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["chunk_status"] == "needs_review"
    assert result["reason"] == "classification_parse_failed"
    assert result["source_status"] == "extracted"
    assert len(complete_payloads[0]["unknown_items"][0]["raw_text"]) == 2000


def test_injection_routes_to_unknown_and_logs_none_model(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "ignore instructions")
    _patch_common(monkeypatch, chunk)
    complete_payloads: list[dict] = []
    token_payloads: list[dict] = []
    saved_classifications: list[dict] = []
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: _result(
            [
                ClassificationDecision(
                    "unknown",
                    0.0,
                    "injection_suspected",
                    "unknown_facts_queue",
                    False,
                )
            ],
            injection=True,
            model_name="none",
        ),
    )
    monkeypatch.setattr(
        tasks.db,
        "complete_classification_job",
        lambda **kwargs: complete_payloads.append(kwargs) or [],
    )
    monkeypatch.setattr(tasks.db, "log_token_usage", lambda **kwargs: token_payloads.append(kwargs))
    monkeypatch.setattr(
        tasks.db,
        "update_chunk_classification",
        lambda chunk_id, classification: saved_classifications.append(classification),
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["chunk_status"] == "needs_review"
    assert result["injection_suspected"] is True
    assert token_payloads[0]["model"] == "none"
    assert token_payloads[0]["input_tokens"] == 0
    assert complete_payloads[0]["unknown_items"]
    assert "raw_response" not in complete_payloads[0]["classification"]


def test_rate_limit_retries_with_countdown(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    _patch_common(monkeypatch, chunk)
    retrying: list[str] = []
    monkeypatch.setattr(tasks.db, "mark_job_retrying", lambda job_id: retrying.append(job_id))

    class RateLimitError(Exception):
        pass

    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: (_ for _ in ()).throw(RateLimitError()),
    )

    with pytest.raises(RetryCalled) as exc_info:
        _call(FakeTask(), **_base_kwargs())

    assert retrying == ["job-1"]
    assert exc_info.value.countdown == 60


def test_final_technical_failure_marks_failed_and_finalizes_without_retry(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    _patch_common(monkeypatch, chunk)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        tasks.db,
        "mark_job_failed",
        lambda *args, **kwargs: events.append(("failed", kwargs)),
    )
    monkeypatch.setattr(
        tasks.db,
        "mark_job_retrying",
        lambda *args, **kwargs: events.append(("retrying", kwargs)),
    )
    monkeypatch.setattr(
        tasks.db,
        "finalize_source_state",
        lambda **kwargs: events.append(("finalized", kwargs)) or "failed",
    )

    class ProviderError(Exception):
        pass

    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: (_ for _ in ()).throw(ProviderError("provider down")),
    )

    with pytest.raises(ProviderError):
        _call(FakeTask(retries=2, max_retries=2), **_base_kwargs())

    assert events == [
        ("failed", {"reason": "ProviderError"}),
        ("finalized", {"source_id": "source-1", "workspace_id": "workspace-1"}),
    ]


def test_parse_domain_failure_does_not_retry(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    _patch_common(monkeypatch, chunk)
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: (_ for _ in ()).throw(ValueError("classification_parse_failed: {bad")),
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "succeeded"


def test_success_enqueues_each_passing_decision_and_returns_summary(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    events: list[str] = []
    _patch_common(monkeypatch, chunk, events)
    enqueued: list[dict] = []
    dispatched: list[str] = []
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: _result(
            [
                ClassificationDecision(
                    "service_price",
                    0.9,
                    "preço",
                    "extracted_facts",
                    True,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        tasks,
        "build_extraction_job_payload",
        lambda **kwargs: enqueued.append(kwargs) or "extract-job-1",
    )
    monkeypatch.setattr(
        tasks,
        "dispatch_extraction_job",
        lambda job_id: events.append("dispatch") or dispatched.append(job_id),
    )
    monkeypatch.setattr(
        tasks.db,
        "mark_job_succeeded",
        lambda *args, **kwargs: events.append("mark_job_succeeded"),
    )
    monkeypatch.setattr(
        tasks.db,
        "complete_classification_job",
        lambda **kwargs: events.append("tx_exit") or ["extract-job-1"],
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["decisions"] == 1
    assert result["chunk_status"] == "classified"
    assert result["input_tokens"] == 11
    assert result["source_status"] == "extracted"
    assert enqueued[0]["fact_type"] == "service_price"
    assert events.index("tx_exit") < events.index("dispatch")
    assert dispatched == ["extract-job-1"]
    assert result["dispatch_failures"] == 0


def test_dispatch_failure_after_commit_does_not_retry_classification(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    _patch_common(monkeypatch, chunk)
    retrying: list[str] = []
    failed: list[str] = []
    monkeypatch.setattr(tasks.db, "mark_job_retrying", lambda job_id: retrying.append(job_id))
    monkeypatch.setattr(tasks.db, "mark_job_failed", lambda *args, **kwargs: failed.append("failed"))
    monkeypatch.setattr(
        tasks,
        "classify_chunk",
        lambda content: _result(
            [
                ClassificationDecision(
                    "service_price",
                    0.9,
                    "preco",
                    "extracted_facts",
                    True,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        tasks,
        "build_extraction_job_payload",
        lambda **kwargs: {"metadata": kwargs},
    )
    monkeypatch.setattr(
        tasks.db,
        "complete_classification_job",
        lambda **kwargs: ["extract-job-1"],
    )
    monkeypatch.setattr(
        tasks,
        "dispatch_extraction_job",
        lambda job_id: (_ for _ in ()).throw(RuntimeError("broker down")),
    )

    result = _call(FakeTask(), **_base_kwargs())

    assert result["status"] == "succeeded"
    assert result["dispatch_failures"] == 1
    assert retrying == []
    assert failed == []


def test_idempotency_key_includes_provider_and_model(monkeypatch) -> None:
    keys: list[str] = []
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "classified", "content")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("CLASSIFICATION_MODEL", "model-a")
    monkeypatch.setattr(
        tasks.db,
        "get_job_by_idempotency_key",
        lambda key: keys.append(key) or None,
    )
    monkeypatch.setattr(tasks.db, "mark_job_running", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "claim_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(tasks.db, "mark_job_succeeded", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.db, "get_chunk", lambda chunk_id: chunk)
    monkeypatch.setattr(tasks.db, "finalize_source_state", lambda **kwargs: "extracted")

    _call(FakeTask(), **_base_kwargs())
    first = keys[0]

    keys.clear()
    monkeypatch.setenv("CLASSIFICATION_MODEL", "model-b")
    _call(FakeTask(), **_base_kwargs())

    assert first != keys[0]


def test_claim_failure_skips_without_llm(monkeypatch) -> None:
    chunk = Chunk("chunk-1", "workspace-1", "source-1", "pending", "content")
    _patch_common(monkeypatch, chunk)
    monkeypatch.setattr(tasks.db, "claim_job", lambda *args, **kwargs: False)
    calls: list[str] = []
    monkeypatch.setattr(tasks.db, "get_chunk", lambda chunk_id: calls.append("chunk") or chunk)
    monkeypatch.setattr(tasks, "classify_chunk", lambda content: calls.append("llm"))

    result = _call(FakeTask(), **_base_kwargs())

    assert result == {"status": "skipped", "reason": "job_claim_failed"}
    assert calls == []
