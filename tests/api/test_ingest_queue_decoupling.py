import builtins
import importlib
import sys
from types import ModuleType
from typing import Any

from observability.context import request_id_context


def test_ingest_queue_import_does_not_import_worker_task(monkeypatch) -> None:
    original_module = sys.modules.get("context_builder.services.ingest_queue")
    sys.modules.pop("context_builder.services.ingest_queue", None)
    sys.modules.pop("worker_ingest.tasks", None)
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "worker_ingest.tasks":
            raise AssertionError("API import should not load worker_ingest.tasks")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    try:
        module = importlib.import_module("context_builder.services.ingest_queue")
    finally:
        if original_module is not None:
            sys.modules["context_builder.services.ingest_queue"] = original_module

    assert hasattr(module, "create_and_enqueue_ingest_job")


class _RpcResult:
    data = "job-123"


class _RpcCall:
    def execute(self) -> _RpcResult:
        return _RpcResult()


class _FakeDb:
    def __init__(self) -> None:
        self.rpc_name: str | None = None
        self.rpc_params: dict[str, Any] | None = None

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcCall:
        self.rpc_name = name
        self.rpc_params = params
        return _RpcCall()


class _CapturingLogger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, Any]]] = []
        self.warning_calls: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.info_calls.append((event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self.warning_calls.append((event, fields))


def test_create_job_preserves_request_id_in_metadata_and_enqueue(monkeypatch) -> None:
    from context_builder.services import ingest_queue

    db = _FakeDb()
    logger = _CapturingLogger()
    enqueued: dict[str, Any] = {}

    def capture_enqueue(**kwargs: Any) -> None:
        enqueued.update(kwargs)

    monkeypatch.setattr(ingest_queue, "enqueue_ingest_source", capture_enqueue)
    monkeypatch.setattr(ingest_queue, "get_logger", lambda service: logger)

    with request_id_context("req-abc"):
        job_id = ingest_queue.create_and_enqueue_ingest_job(
            source_id="source-1",
            workspace_id="workspace-1",
            storage_path="storage/path",
            declared_mime="text/plain",
            file_hash="hash-1",
            actor_user_id="user-1",
            db=db,
        )

    assert job_id == "job-123"
    assert db.rpc_name == "get_or_create_processing_job"
    assert db.rpc_params is not None
    assert db.rpc_params["job_metadata"]["request_id"] == "req-abc"
    assert enqueued["request_id"] == "req-abc"
    assert enqueued["job_id"] == "job-123"
    assert logger.info_calls == [
        (
            "api-agent.ingest.enqueue.queued",
            {
                "agent": "api-agent",
                "stage": "ingest",
                "action": "enqueue",
                "outcome": "queued",
                "request_id": "req-abc",
                "workflow_id": "source-1",
                "job_id": "job-123",
                "workspace_id": "workspace-1",
                "source_id": "source-1",
            },
        )
    ]
    assert logger.warning_calls == []


def test_enqueue_failure_logs_structured_event_and_returns_job_id(monkeypatch) -> None:
    from context_builder.services import ingest_queue

    db = _FakeDb()
    logger = _CapturingLogger()

    def fail_enqueue(**kwargs: Any) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(ingest_queue, "enqueue_ingest_source", fail_enqueue)
    monkeypatch.setattr(ingest_queue, "get_logger", lambda service: logger)

    with request_id_context("req-failed"):
        job_id = ingest_queue.create_and_enqueue_ingest_job(
            source_id="source-2",
            workspace_id="workspace-2",
            storage_path="storage/path",
            declared_mime="text/plain",
            file_hash="hash-2",
            actor_user_id="user-2",
            db=db,
        )

    assert job_id == "job-123"
    assert logger.info_calls == []
    assert logger.warning_calls == [
        (
            "api-agent.ingest.enqueue.failed",
            {
                "agent": "api-agent",
                "stage": "ingest",
                "action": "enqueue",
                "outcome": "failed",
                "request_id": "req-failed",
                "workflow_id": "source-2",
                "job_id": "job-123",
                "workspace_id": "workspace-2",
                "source_id": "source-2",
                "error_type": "RuntimeError",
                "reason": "broker unavailable",
            },
        )
    ]
