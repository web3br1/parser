from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from parsers.base import ExtractedPage, ExtractionResult
from parsers.chunker import RawChunk
from security.file_validator import ValidationResult
from worker_ingest import db, tasks
from worker_ingest.tasks import ingest_source, is_domain_failure


class DummyTask:
    def __init__(self) -> None:
        self.retry_called = False

    def retry(self, *, exc: Exception) -> None:
        self.retry_called = True
        raise exc


def _patch_common(monkeypatch: Any, *, job_status: str = "queued") -> list[str]:
    updates: list[str] = []
    monkeypatch.setattr(db, "get_job", lambda job_id: db.JobRecord(job_id, job_status))
    monkeypatch.setattr(db, "get_job_by_idempotency_key", lambda key: None)
    monkeypatch.setattr(db, "claim_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(db, "get_source", lambda source_id: db.SourceRecord(source_id, "ws_1"))
    monkeypatch.setattr(db, "update_job", lambda job_id, **fields: updates.append(f"job:{fields}"))
    monkeypatch.setattr(
        db,
        "update_source",
        lambda source_id, **fields: updates.append(f"source:{fields}"),
    )
    monkeypatch.setattr(db, "utc_now", lambda: "now")
    monkeypatch.setattr(
        "worker_ingest.tasks.download_from_storage",
        lambda storage_path: storage_path,
    )
    monkeypatch.setattr(db, "complete_ingest_job", lambda **kwargs: None)
    return updates


def test_job_already_succeeded_returns_cached(monkeypatch: Any) -> None:
    _patch_common(monkeypatch, job_status="succeeded")
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path="file.pdf",
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result == {"status": "succeeded", "cached": True}


def test_existing_content_job_returns_cached(monkeypatch: Any) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        db, "get_job_by_idempotency_key", lambda key: db.JobRecord("job_original", "succeeded")
    )
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path="file.pdf",
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result["cached"] is True
    assert result["original_job_id"] == "job_original"


def test_claim_failure_skips_before_download_or_parse(monkeypatch: Any) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(db, "claim_job", lambda *args, **kwargs: False)
    calls: list[str] = []
    monkeypatch.setattr(
        "worker_ingest.tasks.download_from_storage",
        lambda storage_path: calls.append("download") or storage_path,
    )

    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path="file.pdf",
        declared_mime="application/pdf",
        file_hash="hash",
    )

    assert result == {"status": "skipped", "reason": "job_claim_failed"}
    assert calls == []


def test_invalid_file_fails_without_retry(monkeypatch: Any, tmp_path: Path) -> None:
    _patch_common(monkeypatch)
    path = tmp_path / "fake.pdf"
    path.write_text("not pdf", encoding="utf-8")
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path=str(path),
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result["status"] == "failed"
    assert result["reason"] == "magic_bytes_fail"


def test_workspace_mismatch_fails(monkeypatch: Any, tmp_path: Path) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(db, "get_source", lambda source_id: db.SourceRecord(source_id, "other"))
    monkeypatch.setattr(
        "worker_ingest.tasks.validate_file",
        lambda path, mime: ValidationResult(True, None, mime, 1),
    )
    path = tmp_path / "good.pdf"
    path.write_bytes(b"%PDF content")
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path=str(path),
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result["reason"] == "workspace_mismatch"


def test_zero_chunks_fails(monkeypatch: Any, tmp_path: Path) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        "worker_ingest.tasks.validate_file",
        lambda path, mime: ValidationResult(True, None, mime, 1),
    )
    monkeypatch.setattr("worker_ingest.tasks.get_parser", lambda mime: _Parser())
    monkeypatch.setattr("worker_ingest.tasks.chunk_extraction", lambda extraction: [])
    path = tmp_path / "good.pdf"
    path.write_bytes(b"%PDF content")
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path=str(path),
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result["reason"] == "no_chunks_generated"


def test_db_failure_retries(monkeypatch: Any, tmp_path: Path) -> None:
    updates = _patch_common(monkeypatch)
    monkeypatch.setattr(
        "worker_ingest.tasks.validate_file",
        lambda path, mime: ValidationResult(True, None, mime, 1),
    )
    monkeypatch.setattr("worker_ingest.tasks.get_parser", lambda mime: _Parser())
    monkeypatch.setattr("worker_ingest.tasks.chunk_extraction", lambda extraction: [_chunk()])

    monkeypatch.setattr(
        db,
        "complete_ingest_job",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    path = tmp_path / "good.pdf"
    path.write_bytes(b"%PDF content")
    with pytest.raises(RuntimeError):
        ingest_source.run(
            job_id="job_1",
            source_id="src_1",
            workspace_id="ws_1",
            storage_path=str(path),
            declared_mime="application/pdf",
            file_hash="hash",
        )
    assert "job:{'status': 'retrying'}" in updates


def test_final_technical_failure_marks_job_failed_and_source_failed(monkeypatch: Any) -> None:
    events: list[tuple[str, str, dict[str, Any]]] = []
    monkeypatch.setattr(
        db,
        "update_job",
        lambda job_id, **fields: events.append(("job", job_id, fields)),
    )
    monkeypatch.setattr(
        db,
        "update_source",
        lambda source_id, **fields: events.append(("source", source_id, fields)),
    )
    monkeypatch.setattr(db, "utc_now", lambda: "now")
    fake_task = SimpleNamespace(
        max_retries=1,
        request=SimpleNamespace(retries=1),
        retry=lambda exc: (_ for _ in ()).throw(AssertionError("should not retry")),
    )

    result = tasks._retry(fake_task, "job_1", "src_1", "db_transaction_failed", RuntimeError())

    assert result == {"status": "failed", "reason": "db_transaction_failed"}
    assert events == [
        ("source", "src_1", {"status": "failed"}),
        ("job", "job_1", {"status": "failed", "error": "db_transaction_failed", "finished_at": "now"}),
    ]


def test_domain_failure_set() -> None:
    assert is_domain_failure("too_short") is True
    assert is_domain_failure("db_timeout") is False


def test_success_return_contains_counts(monkeypatch: Any, tmp_path: Path) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        "worker_ingest.tasks.validate_file",
        lambda path, mime: ValidationResult(True, None, mime, 1),
    )
    monkeypatch.setattr("worker_ingest.tasks.get_parser", lambda mime: _Parser())
    monkeypatch.setattr("worker_ingest.tasks.chunk_extraction", lambda extraction: [_chunk()])
    monkeypatch.setattr(db, "upsert_quality_report", lambda source_id, workspace_id, report: None)
    monkeypatch.setattr(db, "delete_chunks_by_source", lambda source_id: None)
    monkeypatch.setattr(db, "insert_chunks", lambda source_id, workspace_id, chunks: None)
    path = tmp_path / "good.pdf"
    path.write_bytes(b"%PDF content")
    result = ingest_source.run(
        job_id="job_1",
        source_id="src_1",
        workspace_id="ws_1",
        storage_path=str(path),
        declared_mime="application/pdf",
        file_hash="hash",
    )
    assert result["status"] == "succeeded"
    assert result["chunks_created"] == 1
    assert result["total_chars"] == 120
    assert "warnings" in result


def test_chunk_payload_persists_full_page_span() -> None:
    chunk = RawChunk(
        chunk_index=0,
        text="secao inteira",
        char_count=len("secao inteira"),
        token_estimate=4,
        chunk_hash="hash",
        source_page=2,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading="Procedimento",
        metadata={"parser": "pdf"},
        page_start=2,
        page_end=5,
        section_path="1",
        section_title="Procedimento",
        chunk_kind="numbered_heading",
    )

    payload = db._chunk_payload(chunk)

    assert payload["page_start"] == 2
    assert payload["page_end"] == 5
    assert payload["metadata"]["section_path"] == "1"


class _Parser:
    def extract(self, path: Path) -> ExtractionResult:
        return ExtractionResult(
            mime_type="application/pdf",
            pages=[ExtractedPage(1, "x" * 120, 120, False)],
            total_chars=120,
            metadata={"parser": "pdf"},
        )


def _chunk() -> RawChunk:
    return RawChunk(
        chunk_index=0,
        text="x" * 120,
        char_count=120,
        token_estimate=30,
        chunk_hash="hash",
        source_page=1,
        sheet_name=None,
        row_start=None,
        row_end=None,
        section_heading=None,
        metadata={"parser": "pdf", "source_version": 1, "extraction_timestamp": "now"},
    )
