import pytest
from worker_extraction import db


class _Query:
    def __init__(self) -> None:
        self.payload: dict | None = None
        self.in_filters: list[tuple[str, list[str]]] = []
        self.table_name: str | None = None
        self.rpc_name: str | None = None
        self.rpc_payload: dict | None = None
        self.data: object = None

    def select(self, query: str) -> "_Query":
        return self

    def update(self, payload: dict) -> "_Query":
        self.payload = payload
        return self

    def insert(self, payload: dict) -> "_Query":
        self.payload = payload
        return self

    def eq(self, field: str, value: str) -> "_Query":
        return self

    def in_(self, field: str, values: list[str]) -> "_Query":
        self.in_filters.append((field, values))
        return self

    def maybe_single(self) -> "_Query":
        return self

    def execute(self) -> "_Query":
        return self


class _Client:
    def __init__(self, source_status: str = "extracted") -> None:
        self.query = _Query()
        self.source_status = source_status

    def table(self, name: str) -> _Query:
        self.query.table_name = name
        return self.query

    def rpc(self, name: str, payload: dict) -> _Query:
        self.query.rpc_name = name
        self.query.rpc_payload = payload
        if name == "complete_extraction_job":
            self.query.data = {"records_created": 0, "chunk_status": "extracted"}
        else:
            self.query.data = self.source_status
        return self.query


def test_get_job_by_idempotency_key_treats_missing_response_as_none(monkeypatch):
    monkeypatch.setattr(db, "_client", lambda: _Client())

    assert db.get_job_by_idempotency_key("key") is None


def test_mark_job_running_clears_stale_error(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.mark_job_running("job-id", "idem-key")

    assert client.query.payload is not None
    assert client.query.payload["status"] == "running"
    assert client.query.payload["error_code"] is None
    assert client.query.payload["error_message"] is None


def test_mark_job_succeeded_clears_stale_error(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.mark_job_succeeded("job-id", "idem-key")

    assert client.query.payload is not None
    assert client.query.payload["status"] == "succeeded"
    assert client.query.payload["error_code"] is None
    assert client.query.payload["error_message"] is None


def test_claim_job_uses_status_guard(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.claim_job("job-id", worker_id="worker-a", idempotency_key="idem-key")

    assert client.query.table_name == "processing_jobs"
    assert client.query.payload is not None
    assert client.query.payload["status"] == "running"
    assert client.query.payload["worker_id"] == "worker-a"
    assert ("status", ["queued", "retrying"]) in client.query.in_filters


def test_log_token_usage_uses_database_cost_column(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.log_token_usage(
        workspace_id="workspace-1",
        source_id="source-1",
        chunk_id="chunk-1",
        operation="extraction",
        model="model-1",
        provider="ollama",
        input_tokens=10,
        output_tokens=2,
        estimated_cost_usd=0.25,
        job_id="job-1",
        prompt_version="prompt-v1",
    )

    assert client.query.table_name == "token_usage_log"
    assert client.query.payload is not None
    assert client.query.payload["estimated_cost"] == 0.25
    assert "estimated_cost_usd" not in client.query.payload
    assert client.query.payload["job_id"] == "job-1"
    assert client.query.payload["prompt_version"] == "prompt-v1"


def test_complete_extraction_job_omits_grounding_by_default(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    db.complete_extraction_job(
        job_id="job-1",
        chunk_id="chunk-1",
        workspace_id="workspace-1",
        source_id="source-1",
        chunk_status="extracted",
        idempotency_key="idem-1",
        unknown_item=None,
        evidence_span=None,
        fact_records=[],
        rule_record=None,
    )

    assert client.query.rpc_name == "complete_extraction_job"
    assert client.query.rpc_payload is not None
    assert client.query.rpc_payload["grounding_result"] is None


def test_complete_extraction_job_passes_grounding_result_through(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    grounding_result = {
        "grounding_status": "passed",
        "grounding_required": True,
        "deterministic_status": "passed",
        "match_mode": "normalized",
        "grounding_key": "abc123",
        "config_version": "default@1",
    }

    db.complete_extraction_job(
        job_id="job-1",
        chunk_id="chunk-1",
        workspace_id="workspace-1",
        source_id="source-1",
        chunk_status="extracted",
        idempotency_key="idem-1",
        unknown_item=None,
        evidence_span=None,
        fact_records=[],
        rule_record=None,
        grounding_result=grounding_result,
    )

    assert client.query.rpc_name == "complete_extraction_job"
    assert client.query.rpc_payload is not None
    assert client.query.rpc_payload["grounding_result"] == grounding_result
    # Existing args remain intact and unchanged.
    assert client.query.rpc_payload["target_job_id"] == "job-1"
    assert client.query.rpc_payload["fact_records"] == []


@pytest.mark.parametrize("source_status", ["extracted", "published", "failed"])
def test_finalize_source_state_returns_terminal_status(monkeypatch, source_status):
    client = _Client(source_status)
    monkeypatch.setattr(db, "_client", lambda: client)

    assert db.finalize_source_state("source-1", "workspace-1") == source_status

    assert client.query.rpc_name == "finalize_source_state_after_extraction"
    assert client.query.rpc_payload == {
        "p_source_id": "source-1",
        "p_workspace_id": "workspace-1",
    }
