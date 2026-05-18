from datetime import UTC, datetime
from typing import Any

from worker_ingest import db


class _Table:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.in_filters: list[tuple[str, list[str]]] = []
        self.table_name: str | None = None

    def update(self, payload: dict[str, Any]) -> "_Table":
        self.payload = payload
        return self

    def eq(self, field: str, value: str) -> "_Table":
        return self

    def in_(self, field: str, values: list[str]) -> "_Table":
        self.in_filters.append((field, values))
        return self

    def execute(self) -> "_Result":
        return _Result([{"id": "job_1"}])


class _Client:
    def __init__(self) -> None:
        self.table_obj = _Table()

    def table(self, name: str) -> _Table:
        self.table_obj.table_name = name
        return self.table_obj


def test_update_job_serializes_datetime_fields(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.update_job("job_1", status="running", started_at=datetime(2026, 5, 11, tzinfo=UTC))

    assert client.table_obj.payload == {
        "status": "running",
        "started_at": "2026-05-11T00:00:00+00:00",
    }


def test_claim_job_uses_status_guard(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)
    monkeypatch.setattr(db, "utc_now", lambda: datetime(2026, 5, 11, tzinfo=UTC))

    assert db.claim_job("job_1", worker_id="worker-a", idempotency_key="idem-key") is True

    assert client.table_obj.table_name == "processing_jobs"
    assert client.table_obj.payload is not None
    assert client.table_obj.payload["status"] == "running"
    assert client.table_obj.payload["worker_id"] == "worker-a"
    assert client.table_obj.payload["idempotency_key"] == "idem-key"
    assert ("status", ["queued", "retrying"]) in client.table_obj.in_filters


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self) -> None:
        self.rpc_name: str | None = None

    def select(self, query: str) -> "_Query":
        return self

    def eq(self, field: str, value: str) -> "_Query":
        return self

    def execute(self) -> _Result:
        if self.rpc_name == "get_or_create_processing_job":
            return _Result("job-classification-1")
        return _Result([{"id": "chunk-1"}])


class _DispatchClient:
    def __init__(self) -> None:
        self.query = _Query()

    def table(self, name: str) -> _Query:
        return self.query

    def rpc(self, name: str, payload: dict[str, Any]) -> _Query:
        self.query.rpc_name = name
        return self.query


def test_dispatch_classification_jobs_calls_task_directly_in_eager_mode(monkeypatch):
    delayed: list[dict[str, Any]] = []
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setattr(db, "_client", lambda: _DispatchClient())
    monkeypatch.setattr(
        "worker_classification.tasks.classify_chunk_task.delay",
        lambda **kwargs: delayed.append(kwargs),
    )

    job_ids = db.dispatch_classification_jobs(
        source_id="source-1",
        workspace_id="workspace-1",
        request_id="request-1",
    )

    assert job_ids == ["job-classification-1"]
    assert delayed == [
        {
            "chunk_id": "chunk-1",
            "workspace_id": "workspace-1",
            "source_id": "source-1",
            "job_id": "job-classification-1",
            "request_id": "request-1",
        }
    ]


def test_dispatch_classification_jobs_routes_to_classification_queue(monkeypatch):
    sent: list[tuple[str, dict[str, Any], str | None]] = []
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.setattr(db, "_client", lambda: _DispatchClient())
    from worker_ingest.celery_app import app  # noqa: PLC0415

    monkeypatch.setattr(
        app,
        "send_task",
        lambda name, kwargs, queue=None: sent.append((name, kwargs, queue)),
    )

    db.dispatch_classification_jobs(
        source_id="source-1",
        workspace_id="workspace-1",
        request_id="request-1",
    )

    assert sent == [
        (
            "worker_classification.tasks.classify_chunk_task",
            {
                "chunk_id": "chunk-1",
                "workspace_id": "workspace-1",
                "source_id": "source-1",
                "job_id": "job-classification-1",
                "request_id": "request-1",
            },
            "classification",
        )
    ]
