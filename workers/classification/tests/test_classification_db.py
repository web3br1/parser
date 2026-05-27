from worker_classification import db


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
    def __init__(self) -> None:
        self.query = _Query()

    def table(self, name: str) -> _Query:
        self.query.table_name = name
        return self.query

    def rpc(self, name: str, payload: dict) -> _Query:
        self.query.rpc_name = name
        self.query.rpc_payload = payload
        self.query.data = "extracted"
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
        operation="classification",
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


def test_finalize_source_state_calls_rpc(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "_client", lambda: client)

    assert db.finalize_source_state("source-1", "workspace-1") == "extracted"

    assert client.query.rpc_name == "finalize_source_state_after_extraction"
    assert client.query.rpc_payload == {
        "p_source_id": "source-1",
        "p_workspace_id": "workspace-1",
    }
