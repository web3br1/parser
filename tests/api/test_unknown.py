from __future__ import annotations

import sys
import types
from typing import Any
from uuid import uuid4

import pytest
from context_builder.config import get_settings
from context_builder.dependencies import (
    get_current_user,
    get_supabase_service_for_backend_only,
    require_review_role,
    require_workspace_member,
)
from context_builder.main import create_app
from context_builder.services import unknown_service
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

WORKSPACE_ID = "ws_1"
USER_ID = "user_1"

_REVIEWER_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "u@test.com"},
    "role": "reviewer",
    "workspace_id": WORKSPACE_ID,
}


# ── Mock DB ───────────────────────────────────────────────────────────────────

class Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


class RpcCall:
    def __init__(self, db: UnknownDB, should_raise: str | None = None) -> None:
        self.db = db
        self.should_raise = should_raise

    def execute(self) -> Result:
        if self.should_raise:
            raise Exception(self.should_raise)
        return Result(self.db.rpc_return)


class UnknownQuery:
    def __init__(self, db: UnknownDB, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self.filters: dict[str, Any] = {}
        self.range_start: int | None = None
        self.range_end: int | None = None

    def select(self, _q: str, **_kwargs: Any) -> UnknownQuery:
        return self

    def eq(self, field: str, value: Any) -> UnknownQuery:
        self.filters[field] = value
        return self

    def order(self, _field: str, **_kw: Any) -> UnknownQuery:
        return self

    def maybe_single(self) -> UnknownQuery:
        return self

    def range(self, start: int, end: int) -> UnknownQuery:
        self.range_start = start
        self.range_end = end
        self.db.ranges.append((start, end))
        return self

    def execute(self) -> Result:
        if self.table_name != "unknown_facts_queue":
            return Result(None)

        item_id = self.filters.get("id")
        status_filter = self.filters.get("status")

        if item_id:
            item = self.db.items.get(item_id)
            return Result(item)

        items = list(self.db.items.values())
        ws = self.filters.get("workspace_id")
        if ws:
            items = [i for i in items if i["workspace_id"] == ws]
        if status_filter:
            items = [i for i in items if i["status"] == status_filter]
        count = len(items)
        if self.range_start is not None and self.range_end is not None:
            items = items[self.range_start : self.range_end + 1]
        return Result(items, count=count)


class UnknownDB:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_return: Any = str(uuid4())
        self.rpc_raise_for: dict[str, str] = {}
        self.ranges: list[tuple[int, int]] = []

    def table(self, name: str) -> UnknownQuery:
        return UnknownQuery(self, name)

    def rpc(self, name: str, payload: dict[str, Any]) -> RpcCall:
        self.rpc_calls.append((name, payload))
        return RpcCall(self, self.rpc_raise_for.get(name))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()


def _client_reviewer(db: Any) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID, "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_review_role] = lambda: _REVIEWER_MEMBERSHIP
    return TestClient(app)


def _add_item(
    db: UnknownDB,
    item_id: str,
    *,
    workspace_id: str = WORKSPACE_ID,
    status: str = "open",
) -> None:
    db.items[item_id] = {
        "id": item_id,
        "workspace_id": workspace_id,
        "chunk_id": str(uuid4()),
        "source_id": str(uuid4()),
        "status": status,
        "raw_text": "texto desconhecido",
        "suggested_fact_type": None,
        "confidence": None,
        "resolution": None,
        "resolved_by": None,
        "resolved_at": None,
        "created_at": "2026-05-07T00:00:00+00:00",
    }


def _stub_worker_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub worker_classification so dispatch_extraction_job is importable."""
    fake_mod = types.ModuleType("worker_classification")
    fake_ext = types.ModuleType("worker_classification.extraction_queue")
    fake_ext.dispatch_extraction_job = lambda jid: None  # type: ignore[attr-defined]
    sys.modules.setdefault("worker_classification", fake_mod)
    sys.modules["worker_classification.extraction_queue"] = fake_ext


class _SpyLogger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, Any]]] = []
        self.warnings: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.infos.append((event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self.warnings.append((event, fields))


# ── Authentication ────────────────────────────────────────────────────────────

def test_get_unknown_without_bearer_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = TestClient(create_app()).get(f"/workspaces/{WORKSPACE_ID}/unknown")
    assert response.status_code == 401


def test_get_unknown_with_staff_role_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: UnknownDB()
    app.dependency_overrides[require_workspace_member] = lambda: {
        "user": {"id": USER_ID},
        "role": "staff",
        "workspace_id": WORKSPACE_ID,
    }
    response = TestClient(app).get(f"/workspaces/{WORKSPACE_ID}/unknown")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


# ── Unknown queue listing ─────────────────────────────────────────────────────

def test_get_unknown_queue_returns_paginated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    monkeypatch.setattr(
        unknown_service,
        "get_unknown_queue",
        lambda db, **kw: {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0},
    )
    response = _client_reviewer(UnknownDB()).get(f"/workspaces/{WORKSPACE_ID}/unknown")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["total"] == 0


def test_get_unknown_queue_status_filter_passed_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    captured: list[dict] = []

    def _mock(db: Any, **kw: Any) -> dict:
        captured.append(kw)
        return {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0}

    monkeypatch.setattr(unknown_service, "get_unknown_queue", _mock)
    _client_reviewer(UnknownDB()).get(f"/workspaces/{WORKSPACE_ID}/unknown?status=open")
    assert captured[0]["status_filter"] == "open"


def test_get_unknown_queue_uses_database_range_and_count() -> None:
    db = UnknownDB()
    for index in range(25):
        _add_item(db, f"item_{index}")

    result = unknown_service.get_unknown_queue(
        db,
        workspace_id=WORKSPACE_ID,
        page=2,
        per_page=10,
        status_filter="open",
    )

    assert db.ranges == [(10, 19)]
    assert result["total"] == 25
    assert result["pages"] == 3
    assert len(result["items"]) == 10


# ── Reclassify ────────────────────────────────────────────────────────────────

def test_reclassify_returns_mapped_with_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    job_id = str(uuid4())
    monkeypatch.setattr(
        unknown_service,
        "reclassify_unknown",
        lambda db, **kw: {"status": "mapped", "extraction_job_id": job_id},
    )

    item_id = str(uuid4())
    response = _client_reviewer(UnknownDB()).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "extracted_facts"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "mapped"
    assert body["extraction_job_id"] == job_id


def test_reclassify_calls_rpc_reclassify_unknown_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calls the real reclassify_unknown service directly with mock DB."""
    _env(monkeypatch)
    _stub_worker_classification(monkeypatch)

    db = UnknownDB()
    item_id = str(uuid4())
    job_id = str(uuid4())
    db.rpc_return = job_id
    _add_item(db, item_id)

    from context_builder.services.unknown_service import reclassify_unknown  # noqa: PLC0415

    result = reclassify_unknown(
        db,
        workspace_id=WORKSPACE_ID,
        item_id=item_id,
        fact_type="service_price",
        destination="extracted_facts",
        reviewer_id=USER_ID,
        note=None,
    )

    assert result["status"] == "mapped"
    assert result["extraction_job_id"] == job_id

    rpc_names = [n for n, _ in db.rpc_calls]
    assert "reclassify_unknown_item" in rpc_names

    rpc_payload = next(p for n, p in db.rpc_calls if n == "reclassify_unknown_item")
    assert rpc_payload["p_item_id"] == item_id
    assert rpc_payload["p_fact_type"] == "service_price"
    assert rpc_payload["p_chunk_id"] == db.items[item_id]["chunk_id"]
    assert rpc_payload["p_source_id"] == db.items[item_id]["source_id"]
    assert rpc_payload["p_confidence"] == 0.5
    assert rpc_payload["p_actor_user_id"] == USER_ID


def test_reclassify_emits_structured_review_agent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    _stub_worker_classification(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    job_id = str(uuid4())
    db.rpc_return = job_id
    _add_item(db, item_id)
    spy = _SpyLogger()
    monkeypatch.setattr(unknown_service, "logger", spy)

    unknown_service.reclassify_unknown(
        db,
        workspace_id=WORKSPACE_ID,
        item_id=item_id,
        fact_type="service_price",
        destination="extracted_facts",
        reviewer_id=USER_ID,
        note=None,
    )

    assert spy.infos == [(
        "review-agent.unknown.reclassify.succeeded",
        {
            "agent": "review-agent",
            "stage": "unknown",
            "action": "reclassify",
            "outcome": "succeeded",
            "workspace_id": WORKSPACE_ID,
            "resource_type": "unknown_fact",
            "resource_id": item_id,
            "item_id": item_id,
            "actor_user_id": USER_ID,
            "job_id": job_id,
            "fact_type": "service_price",
            "destination": "extracted_facts",
        },
    )]


def test_reclassify_rejects_invalid_fact_destination_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "business_rules"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_destination_for_fact_type"
    assert not any(n == "reclassify_unknown_item" for n, _ in db.rpc_calls)


def test_reclassify_dispatch_called_after_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)

    call_order: list[str] = []

    def _fake_dispatch(jid: str) -> None:
        call_order.append(f"dispatch:{jid}")

    fake_mod = types.ModuleType("worker_classification")
    fake_ext = types.ModuleType("worker_classification.extraction_queue")
    fake_ext.dispatch_extraction_job = _fake_dispatch  # type: ignore[attr-defined]
    sys.modules.setdefault("worker_classification", fake_mod)
    sys.modules["worker_classification.extraction_queue"] = fake_ext

    db = UnknownDB()
    item_id = str(uuid4())
    job_id = str(uuid4())
    db.rpc_return = job_id
    _add_item(db, item_id)

    original_rpc = db.rpc

    def _tracking_rpc(name: str, payload: dict) -> Any:
        call_order.append(f"rpc:{name}")
        return original_rpc(name, payload)

    db.rpc = _tracking_rpc  # type: ignore[method-assign]

    from context_builder.services.unknown_service import reclassify_unknown  # noqa: PLC0415

    reclassify_unknown(
        db,
        workspace_id=WORKSPACE_ID,
        item_id=item_id,
        fact_type="service_price",
        destination="extracted_facts",
        reviewer_id=USER_ID,
        note=None,
    )

    rpc_idx = next(i for i, s in enumerate(call_order) if s.startswith("rpc:reclassify"))
    dispatch_idx = next(
        (i for i, s in enumerate(call_order) if s.startswith("dispatch:")), None
    )
    if dispatch_idx is not None:
        assert rpc_idx < dispatch_idx


def test_reclassify_invalid_fact_type_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "nonexistent_type", "destination": "extracted_facts"},
    )

    assert response.status_code == 422
    assert not any(n == "reclassify_unknown_item" for n, _ in db.rpc_calls)


def test_reclassify_invalid_destination_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "invalid_table"},
    )

    assert response.status_code == 422
    assert not any(n == "reclassify_unknown_item" for n, _ in db.rpc_calls)


def test_reclassify_already_mapped_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, status="mapped")
    db.rpc_raise_for["reclassify_unknown_item"] = "already_mapped"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "extracted_facts"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "already_mapped"


def test_reclassify_already_ignored_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, status="ignored")
    db.rpc_raise_for["reclassify_unknown_item"] = "already_ignored"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "extracted_facts"},
    )

    assert response.status_code == 409


def test_reclassify_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, workspace_id="other_ws")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/reclassify",
        json={"fact_type": "service_price", "destination": "extracted_facts"},
    )

    assert response.status_code == 404


def test_reclassify_dispatch_failure_leaves_item_mapped_job_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If dispatch raises, the service should not propagate the error."""
    _env(monkeypatch)

    fake_mod = types.ModuleType("worker_classification")
    fake_ext = types.ModuleType("worker_classification.extraction_queue")
    fake_ext.dispatch_extraction_job = lambda jid: (_ for _ in ()).throw(RuntimeError("broker down"))  # type: ignore[attr-defined]
    sys.modules.setdefault("worker_classification", fake_mod)
    sys.modules["worker_classification.extraction_queue"] = fake_ext

    db = UnknownDB()
    item_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_item(db, item_id)

    from context_builder.services.unknown_service import reclassify_unknown  # noqa: PLC0415

    result = reclassify_unknown(
        db,
        workspace_id=WORKSPACE_ID,
        item_id=item_id,
        fact_type="service_price",
        destination="extracted_facts",
        reviewer_id=USER_ID,
        note=None,
    )

    assert result["status"] == "mapped"
    assert any(n == "reclassify_unknown_item" for n, _ in db.rpc_calls)


def test_reclassify_dispatch_failure_emits_structured_skipped_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)

    fake_mod = types.ModuleType("worker_classification")
    fake_ext = types.ModuleType("worker_classification.extraction_queue")
    fake_ext.dispatch_extraction_job = lambda jid: (_ for _ in ()).throw(RuntimeError("broker down"))  # type: ignore[attr-defined]
    sys.modules.setdefault("worker_classification", fake_mod)
    sys.modules["worker_classification.extraction_queue"] = fake_ext

    db = UnknownDB()
    item_id = str(uuid4())
    job_id = str(uuid4())
    db.rpc_return = job_id
    _add_item(db, item_id)
    spy = _SpyLogger()
    monkeypatch.setattr(unknown_service, "logger", spy)

    unknown_service.reclassify_unknown(
        db,
        workspace_id=WORKSPACE_ID,
        item_id=item_id,
        fact_type="service_price",
        destination="extracted_facts",
        reviewer_id=USER_ID,
        note=None,
    )

    assert spy.warnings[0][0] == "review-agent.unknown.dispatch.skipped"
    assert spy.warnings[0][1]["action"] == "dispatch"
    assert spy.warnings[0][1]["outcome"] == "skipped"
    assert spy.warnings[0][1]["job_id"] == job_id


# ── Ignore ────────────────────────────────────────────────────────────────────

def test_ignore_returns_ignored_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore", json={}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_ignore_calls_rpc_ignore_unknown_item(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore",
        json={"note": "not relevant"},
    )

    assert any(n == "ignore_unknown_item" for n, _ in db.rpc_calls)
    rpc_payload = next(p for n, p in db.rpc_calls if n == "ignore_unknown_item")
    assert rpc_payload["p_item_id"] == item_id
    assert rpc_payload["p_reason"] == "not relevant"
    assert rpc_payload["p_actor_user_id"] == USER_ID


def test_ignore_emits_structured_review_agent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id)
    spy = _SpyLogger()
    monkeypatch.setattr(unknown_service, "logger", spy)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore", json={}
    )

    assert spy.infos[0][0] == "review-agent.unknown.ignore.succeeded"
    assert spy.infos[0][1]["action"] == "ignore"
    assert spy.infos[0][1]["resource_id"] == item_id
    assert spy.infos[0][1]["actor_user_id"] == USER_ID


def test_ignore_is_idempotent_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, status="ignored")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore", json={}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_ignore_already_mapped_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, status="mapped")
    db.rpc_raise_for["ignore_unknown_item"] = "already_mapped"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore", json={}
    )

    assert response.status_code == 409


def test_ignore_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = UnknownDB()
    item_id = str(uuid4())
    _add_item(db, item_id, workspace_id="other_ws")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/unknown/{item_id}/ignore", json={}
    )

    assert response.status_code == 404
