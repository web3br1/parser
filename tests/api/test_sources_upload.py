import json
from hashlib import sha256
from io import BytesIO
from typing import Any

import pytest
from context_builder.config import get_settings
from context_builder.dependencies import (
    get_current_user,
    get_supabase_service_for_backend_only,
    require_upload_permission,
    require_workspace_member,
)
from context_builder.main import create_app
from context_builder.routers import sources
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from security.file_validator import FileRejectionReason, ValidationResult


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: "SourcesDB", table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}
        self.limit_value: int | None = None

    def select(self, query: str) -> "Query":
        return self

    def insert(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def eq(self, field: str, value: Any) -> "Query":
        self.filters[field] = value
        self.db.filters.append((self.table, field, value))
        return self

    def is_(self, field: str, value: Any) -> "Query":
        self.filters[field] = value
        self.db.filters.append((self.table, field, value))
        return self

    def order(self, field: str, desc: bool = False) -> "Query":
        return self

    def limit(self, value: int) -> "Query":
        self.limit_value = value
        return self

    def maybe_single(self) -> "Query":
        self.db.maybe_single_called = True
        return self

    def execute(self) -> Result | None:
        if self.table == "sources":
            return self._execute_sources()
        if self.table == "processing_jobs":
            return self._execute_jobs()
        return Result(None)

    def _execute_sources(self) -> Result | None:
        if self.payload and "id" in self.filters:
            self.db.source_updates.append((self.filters["id"], self.payload))
            return Result([self.payload])

        if self.payload:
            source_id = f"src_{len(self.db.sources) + 1}"
            row = {
                "id": source_id,
                "workspace_id": self.payload["workspace_id"],
                "status": self.payload["status"],
                "title": None,
                "original_filename": self.payload.get("original_filename"),
                "mime_type": self.payload.get("mime_type"),
                "file_size_bytes": self.payload.get("file_size_bytes"),
                "file_hash": self.payload.get("file_hash"),
                "created_at": "2026-05-06T00:00:00+00:00",
            }
            self.db.sources.append(row)
            return Result([row])

        if "file_hash" in self.filters and self.db.duplicate_source:
            return Result(self.db.duplicate_source)
        if "file_hash" in self.filters and self.db.return_none_for_missing_maybe_single:
            return None

        rows = [
            row
            for row in self.db.sources
            if row["workspace_id"] == self.filters.get("workspace_id", row["workspace_id"])
        ]
        if self.filters.get("deleted_at") == "null":
            rows = [row for row in rows if row.get("deleted_at") is None]
        if "id" in self.filters:
            rows = [row for row in rows if row["id"] == self.filters["id"]]
            return Result(rows[0] if rows else None)
        return Result(rows)

    def _execute_jobs(self) -> Result:
        if self.payload:
            if self.db.fail_job_insert:
                raise RuntimeError("job insert failed")
            job_id = f"job_{len(self.db.jobs) + 1}"
            row = {"id": job_id, **self.payload}
            self.db.jobs.append(row)
            return Result([row])

        rows = [
            row
            for row in self.db.jobs
            if row["source_id"] == self.filters.get("source_id")
            and row["workspace_id"] == self.filters.get("workspace_id")
        ]
        return Result(rows[0] if rows else None)


class SourcesDB:
    def __init__(self) -> None:
        self.sources: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []
        self.source_updates: list[tuple[str, dict[str, Any]]] = []
        self.filters: list[tuple[str, str, Any]] = []
        self.duplicate_source: dict[str, Any] | None = None
        self.fail_job_insert = False
        self.maybe_single_called = False
        self.return_none_for_missing_maybe_single = False

    def table(self, name: str) -> Query:
        return Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> "SourcesDB":
        self.rpc_name = name
        self.rpc_params = params
        return self

    def execute(self) -> Result:
        if hasattr(self, "rpc_name") and self.rpc_name == "get_or_create_processing_job":
            if self.fail_job_insert:
                raise RuntimeError("job insert failed")
            job_id = f"job_{len(self.jobs) + 1}"
            row = {
                "id": job_id,
                "workspace_id": self.rpc_params["target_workspace_id"],
                "source_id": self.rpc_params["target_source_id"],
                "job_type": self.rpc_params["target_job_type"],
                "idempotency_key": self.rpc_params["target_idempotency_key"],
                "metadata": self.rpc_params["job_metadata"],
                "status": "queued",
                "created_at": "2026-05-06T00:00:00+00:00",
            }
            self.jobs.append(row)
            return Result(job_id)
        return Result(None)


def _client(db: SourcesDB, role: str = "manager") -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user_1", "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_upload_permission] = lambda: {
        "user": {"id": "user_1"},
        "role": role,
        "workspace_id": "ws_1",
    }
    app.dependency_overrides[require_workspace_member] = lambda: {
        "user": {"id": "user_1"},
        "role": role,
        "workspace_id": "ws_1",
    }
    return TestClient(app)


def _pdf_file() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("menu.pdf", b"%PDF valid content", "application/pdf")}


def _valid_validation(path, mime: str) -> ValidationResult:
    return ValidationResult(True, None, mime, 123)


def test_upload_without_bearer_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()

    response = TestClient(create_app()).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 401


def test_staff_and_reviewer_cannot_upload(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    for role in ("staff", "reviewer"):
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: {"id": "user_1"}
        app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: SourcesDB()
        app.dependency_overrides[require_workspace_member] = lambda role=role: {
            "user": {"id": "user_1"},
            "role": role,
            "workspace_id": "ws_1",
        }
        response = TestClient(app).post(
            "/workspaces/ws_1/sources/upload",
            files=_pdf_file(),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "insufficient_role"


def test_valid_manager_upload_enqueues_with_storage_path(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    uploaded: list[dict[str, Any]] = []
    delayed: list[dict[str, Any]] = []
    monkeypatch.setattr(sources, "validate_file", _valid_validation)
    monkeypatch.setattr(sources, "upload_to_storage", lambda **kwargs: uploaded.append(kwargs))
    monkeypatch.setitem(
        sources.create_and_enqueue_ingest_job.__globals__,
        "enqueue_ingest_source",
        lambda **kwargs: delayed.append(kwargs),
    )

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 202
    assert response.json()["source_id"] == "src_1"
    assert response.json()["job_id"] == "job_1"
    assert uploaded[0]["path"] == "workspaces/ws_1/sources/src_1/original.pdf"
    assert delayed[0]["storage_path"] == "workspaces/ws_1/sources/src_1/original.pdf"
    assert "file_path" not in delayed[0]
    expected_key_payload = b"ingest:src_1:" + sha256(b"%PDF valid content").hexdigest().encode()
    assert db.jobs[0]["idempotency_key"] == sha256(expected_key_payload).hexdigest()
    assert db.jobs[0]["metadata"]["chunks_created"] is None


def test_upload_logs_enqueue_failure_details(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    monkeypatch.setattr(sources, "validate_file", _valid_validation)
    monkeypatch.setattr(sources, "upload_to_storage", lambda **kwargs: None)

    def fail_enqueue(**kwargs: Any) -> None:
        raise RuntimeError("filesystem broker missing")

    monkeypatch.setitem(
        sources.create_and_enqueue_ingest_job.__globals__,
        "enqueue_ingest_source",
        fail_enqueue,
    )

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 202
    log_lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    enqueue_failure = next(
        line for line in log_lines if line["event"] == "api-agent.ingest.enqueue.failed"
    )
    assert enqueue_failure["job_id"] == "job_1"
    assert enqueue_failure["workflow_id"] == "src_1"
    assert enqueue_failure["workspace_id"] == "ws_1"
    assert enqueue_failure["source_id"] == "src_1"
    assert enqueue_failure["error_type"] == "RuntimeError"
    assert enqueue_failure["reason"] == "filesystem broker missing"
    assert enqueue_failure["agent"] == "api-agent"
    assert enqueue_failure["stage"] == "ingest"
    assert enqueue_failure["action"] == "enqueue"
    assert enqueue_failure["outcome"] == "failed"


def test_upload_allows_missing_duplicate_query_response(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.return_none_for_missing_maybe_single = True
    delayed: list[dict[str, Any]] = []
    monkeypatch.setattr(sources, "validate_file", _valid_validation)
    monkeypatch.setattr(sources, "upload_to_storage", lambda **kwargs: None)
    monkeypatch.setitem(
        sources.create_and_enqueue_ingest_job.__globals__,
        "enqueue_ingest_source",
        lambda **kwargs: delayed.append(kwargs),
    )

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 202
    assert response.json()["source_id"] == "src_1"
    assert delayed[0]["source_id"] == "src_1"


def test_fake_pdf_returns_magic_bytes_reason(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    monkeypatch.setattr(
        sources,
        "validate_file",
        lambda path, mime: ValidationResult(
            False,
            FileRejectionReason.MAGIC_BYTES_FAIL,
            "text/plain",
            10,
        ),
    )

    response = _client(SourcesDB()).post(
        "/workspaces/ws_1/sources/upload",
        files={"file": ("fake.pdf", b"not pdf", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "magic_bytes_fail"


def test_duplicate_file_returns_409(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.duplicate_source = {"id": "src_existing", "status": "uploaded"}

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 409
    assert response.json()["detail"]["existing_source_id"] == "src_existing"


def test_upload_rejects_content_length_above_limit(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", "1")
    get_settings.cache_clear()

    response = _client(SourcesDB()).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 413
    assert response.json()["detail"] == "file_too_large"


@pytest.mark.anyio
async def test_streaming_reader_stops_when_bytes_exceed_limit() -> None:
    upload = UploadFile(
        filename="large.pdf",
        file=BytesIO(b"%PDF too much content"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(HTTPException) as exc:
        await sources._read_upload_to_spooled_file(upload, max_file_size_bytes=4)

    assert exc.value.status_code == 413
    assert exc.value.detail == "file_too_large"


def test_storage_failure_marks_source_failed_without_delete(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    deleted: list[str] = []
    monkeypatch.setattr(sources, "validate_file", _valid_validation)
    monkeypatch.setattr(
        sources,
        "upload_to_storage",
        lambda **kwargs: (_ for _ in ()).throw(HTTPException(500, "storage_upload_failed")),
    )
    monkeypatch.setattr(sources, "delete_from_storage", lambda path: deleted.append(path))

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 500
    assert deleted == []
    assert db.source_updates[-1][1]["status"] == "failed"
    assert db.source_updates[-1][1]["deleted_at"] is not None


def test_job_insert_failure_deletes_uploaded_file(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.fail_job_insert = True
    deleted: list[str] = []
    monkeypatch.setattr(sources, "validate_file", _valid_validation)
    monkeypatch.setattr(sources, "upload_to_storage", lambda **kwargs: None)
    monkeypatch.setattr(sources, "delete_from_storage", lambda path: deleted.append(path))

    response = _client(db).post("/workspaces/ws_1/sources/upload", files=_pdf_file())

    assert response.status_code == 500
    assert deleted == ["workspaces/ws_1/sources/src_1/original.pdf"]
    assert db.source_updates[-1][1]["status"] == "failed"
    assert db.source_updates[-1][1]["deleted_at"] is not None


def test_get_source_from_other_workspace_returns_404(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.sources.append(
        {
            "id": "src_other",
            "workspace_id": "other",
            "status": "uploaded",
            "title": None,
            "original_filename": "x.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1,
            "created_at": "2026-05-06T00:00:00+00:00",
        }
    )

    response = _client(db).get("/workspaces/ws_1/sources/src_other")

    assert response.status_code == 404


def test_get_deleted_source_returns_404(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.sources.append(
        {
            "id": "src_deleted",
            "workspace_id": "ws_1",
            "status": "uploaded",
            "title": None,
            "original_filename": "deleted.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1,
            "deleted_at": "2026-05-06T00:00:00+00:00",
            "created_at": "2026-05-06T00:00:00+00:00",
        }
    )

    response = _client(db).get("/workspaces/ws_1/sources/src_deleted")

    assert response.status_code == 404
    assert ("sources", "deleted_at", "null") in db.filters


def test_get_source_job_from_other_workspace_returns_404(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.jobs.append(
        {
            "id": "job_other",
            "workspace_id": "other",
            "source_id": "src_other",
            "job_type": "ingest",
            "status": "failed",
            "started_at": None,
            "finished_at": None,
            "error_message": "parse_failed",
            "metadata": {"chunks_created": None},
        }
    )

    response = _client(db).get("/workspaces/ws_1/sources/src_other/job")

    assert response.status_code == 404
    assert response.json()["detail"] == "job_not_found"


def test_get_deleted_source_job_returns_404(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.sources.append(
        {
            "id": "src_deleted",
            "workspace_id": "ws_1",
            "status": "uploaded",
            "title": None,
            "original_filename": "deleted.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1,
            "deleted_at": "2026-05-06T00:00:00+00:00",
            "created_at": "2026-05-06T00:00:00+00:00",
        }
    )
    db.jobs.append(
        {
            "id": "job_deleted",
            "workspace_id": "ws_1",
            "source_id": "src_deleted",
            "job_type": "ingest",
            "status": "failed",
            "started_at": None,
            "finished_at": None,
            "error_message": "parse_failed",
            "metadata": {"chunks_created": None},
        }
    )

    response = _client(db).get("/workspaces/ws_1/sources/src_deleted/job")

    assert response.status_code == 404
    assert response.json()["detail"] == "job_not_found"


def test_list_sources_never_returns_other_workspace_rows(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.sources.extend(
        [
            {
                "id": "src_ws_1",
                "workspace_id": "ws_1",
                "status": "uploaded",
                "title": None,
                "original_filename": "ours.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 1,
                "created_at": "2026-05-06T00:00:00+00:00",
            },
            {
                "id": "src_other",
                "workspace_id": "other",
                "status": "uploaded",
                "title": None,
                "original_filename": "theirs.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 1,
                "created_at": "2026-05-06T00:00:00+00:00",
            },
        ]
    )

    response = _client(db).get("/workspaces/ws_1/sources")

    assert response.status_code == 200
    assert [source["id"] for source in response.json()] == ["src_ws_1"]
    assert ("sources", "workspace_id", "ws_1") in db.filters


def test_get_source_job_uses_error_message(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    db = SourcesDB()
    db.sources.append(
        {
            "id": "src_1",
            "workspace_id": "ws_1",
            "status": "uploaded",
            "title": None,
            "original_filename": "ours.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1,
            "created_at": "2026-05-06T00:00:00+00:00",
        }
    )
    db.jobs.append(
        {
            "id": "job_1",
            "workspace_id": "ws_1",
            "source_id": "src_1",
            "job_type": "ingest",
            "status": "failed",
            "started_at": None,
            "finished_at": None,
            "error_message": "parse_failed",
            "metadata": {"chunks_created": None},
        }
    )

    response = _client(db).get("/workspaces/ws_1/sources/src_1/job")

    assert response.status_code == 200
    assert response.json()["error_message"] == "parse_failed"
    assert "error" not in response.json()
