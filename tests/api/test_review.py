from __future__ import annotations

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
from context_builder.services import review_service
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

WORKSPACE_ID = "ws_1"
USER_ID = "user_1"

_REVIEWER_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "u@test.com"},
    "role": "reviewer",
    "workspace_id": WORKSPACE_ID,
}

_MANAGER_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "u@test.com"},
    "role": "manager",
    "workspace_id": WORKSPACE_ID,
}

# Valid content for service_price fact
_VALID_PRICE = {
    "service_name": "Corte",
    "price_amount": 50.0,
    "currency": "BRL",
    "price_type": "fixed",
}


# ── Mock DB ───────────────────────────────────────────────────────────────────

class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class RpcCall:
    def __init__(self, db: ReviewDB, should_raise: str | None = None) -> None:
        self.db = db
        self.should_raise = should_raise

    def execute(self) -> Result:
        if self.should_raise:
            raise Exception(self.should_raise)
        return Result(self.db.rpc_return)


class ReviewQuery:
    def __init__(self, db: ReviewDB, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self.filters: dict[str, Any] = {}
        self.in_filters: dict[str, list[Any]] = {}
        self.orders: list[tuple[str, bool]] = []
        self.range_args: tuple[int, int] | None = None
        self.count_requested = False

    def select(self, _q: str, **kwargs: Any) -> ReviewQuery:
        self.count_requested = kwargs.get("count") == "exact"
        return self

    def eq(self, field: str, value: Any) -> ReviewQuery:
        self.filters[field] = value
        return self

    def in_(self, field: str, values: list) -> ReviewQuery:
        self.in_filters[field] = values
        return self

    def order(self, field: str, **kw: Any) -> ReviewQuery:
        self.orders.append((field, bool(kw.get("desc"))))
        self.db.operations.append((self.table_name, "order", field, kw))
        return self

    def range(self, start: int, end: int) -> ReviewQuery:
        self.range_args = (start, end)
        self.db.operations.append((self.table_name, "range", start, end))
        return self

    def maybe_single(self) -> ReviewQuery:
        return self

    def execute(self) -> Result:
        self.db.executed_tables.append(self.table_name)
        if self.table_name == "extracted_facts" and self.filters.get("id"):
            fact_id = self.filters.get("id")
            if fact_id and fact_id in self.db.facts:
                return Result(self.db.facts[fact_id])
            return Result(None)
        if self.table_name == "business_rules" and self.filters.get("id"):
            rule_id = self.filters.get("id")
            if rule_id and rule_id in self.db.rules:
                return Result(self.db.rules[rule_id])
            return Result(None)
        rows = list(self.db.rows.get(self.table_name, []))
        for field, value in self.filters.items():
            rows = [r for r in rows if r.get(field) == value]
        for field, values in self.in_filters.items():
            rows = [r for r in rows if r.get(field) in values]
        for field, desc in reversed(self.orders):
            rows.sort(key=lambda r: r.get(field) or "", reverse=desc)
        count = len(rows) if self.count_requested else None
        if self.range_args:
            start, end = self.range_args
            rows = rows[start : end + 1]
        result = Result(rows)
        result.count = count
        return result


class ReviewDB:
    def __init__(self) -> None:
        self.facts: dict[str, dict[str, Any]] = {}
        self.rules: dict[str, dict[str, Any]] = {}
        self.rows: dict[str, list[dict[str, Any]]] = {
            "extracted_facts": [],
            "business_rules": [],
            "unknown_facts_queue": [],
            "chunks": [],
            "sources": [],
        }
        self.executed_tables: list[str] = []
        self.operations: list[tuple[Any, ...]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_return: Any = str(uuid4())
        self.rpc_raise_for: dict[str, str] = {}

    def table(self, name: str) -> ReviewQuery:
        return ReviewQuery(self, name)

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
    app.dependency_overrides[require_workspace_member] = lambda: _REVIEWER_MEMBERSHIP
    app.dependency_overrides[require_review_role] = lambda: _REVIEWER_MEMBERSHIP
    return TestClient(app)


def _client_manager(db: Any) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID, "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: _MANAGER_MEMBERSHIP
    app.dependency_overrides[require_review_role] = lambda: _MANAGER_MEMBERSHIP
    return TestClient(app)


def _add_fact(
    db: ReviewDB,
    fact_id: str,
    *,
    workspace_id: str = WORKSPACE_ID,
    status: str = "extracted",
    fact_type: str = "service_price",
) -> None:
    db.facts[fact_id] = {
        "id": fact_id,
        "workspace_id": workspace_id,
        "status": status,
        "fact_type": fact_type,
    }


def _add_rule(
    db: ReviewDB,
    rule_id: str,
    *,
    workspace_id: str = WORKSPACE_ID,
    status: str = "extracted",
    rule_type: str = "discount_rule",
) -> None:
    db.rules[rule_id] = {
        "id": rule_id,
        "workspace_id": workspace_id,
        "status": status,
        "rule_type": rule_type,
    }


class _SpyLogger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.infos.append((event, fields))


# ── Auth / authorization ──────────────────────────────────────────────────────

def test_get_review_without_bearer_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = TestClient(create_app()).get(f"/workspaces/{WORKSPACE_ID}/review")
    assert response.status_code == 401


def test_get_review_with_staff_role_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID, "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: ReviewDB()
    app.dependency_overrides[require_workspace_member] = lambda: {
        "user": {"id": USER_ID},
        "role": "staff",
        "workspace_id": WORKSPACE_ID,
    }
    response = TestClient(app).get(f"/workspaces/{WORKSPACE_ID}/review")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_get_review_with_reviewer_role_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    monkeypatch.setattr(
        review_service,
        "get_review_queue",
        lambda db, **kw: {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0},
    )
    response = _client_reviewer(ReviewDB()).get(f"/workspaces/{WORKSPACE_ID}/review")
    assert response.status_code == 200


def test_require_review_role_builds_on_require_workspace_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    import inspect  # noqa: PLC0415

    from context_builder.dependencies import require_review_role  # noqa: PLC0415
    src = inspect.getsource(require_review_role)
    assert "require_workspace_member" in src
    assert "REVIEW_ALLOWED_ROLES" in src


# ── Review queue ─────────────────────────────────────────────────────────────

def test_get_review_queue_empty_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    monkeypatch.setattr(
        review_service,
        "get_review_queue",
        lambda db, **kw: {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0},
    )
    response = _client_reviewer(ReviewDB()).get(f"/workspaces/{WORKSPACE_ID}/review")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_get_review_queue_fact_type_filter_passed_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    captured: list[dict] = []

    def _mock(db: Any, **kw: Any) -> dict:
        captured.append(kw)
        return {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0}

    monkeypatch.setattr(review_service, "get_review_queue", _mock)
    _client_reviewer(ReviewDB()).get(
        f"/workspaces/{WORKSPACE_ID}/review?fact_type=service_price"
    )
    assert captured[0]["fact_type"] == "service_price"


def test_get_review_queue_pagination_params_passed_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    captured: list[dict] = []

    def _mock(db: Any, **kw: Any) -> dict:
        captured.append(kw)
        return {"items": [], "total": 0, "page": 2, "per_page": 5, "pages": 0}

    monkeypatch.setattr(review_service, "get_review_queue", _mock)
    _client_reviewer(ReviewDB()).get(
        f"/workspaces/{WORKSPACE_ID}/review?page=2&per_page=5"
    )
    assert captured[0]["page"] == 2
    assert captured[0]["per_page"] == 5


def test_get_chunk_detail_returns_facts_and_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    chunk_id = str(uuid4())
    fake_detail = {
        "chunk_id": chunk_id,
        "source_id": str(uuid4()),
        "source_name": "menu.pdf",
        "chunk_index": 0,
        "content": "texto do chunk",
        "facts": [],
        "rules": [],
    }
    monkeypatch.setattr(
        review_service, "get_chunk_detail", lambda db, **kw: fake_detail,
    )
    response = _client_reviewer(ReviewDB()).get(
        f"/workspaces/{WORKSPACE_ID}/review/{chunk_id}"
    )
    assert response.status_code == 200
    assert response.json()["chunk_id"] == chunk_id


def test_get_chunk_detail_from_other_workspace_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    from fastapi import HTTPException  # noqa: PLC0415

    chunk_id = str(uuid4())
    monkeypatch.setattr(
        review_service,
        "get_chunk_detail",
        lambda db, **kw: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="chunk_not_found")
        ),
    )
    response = _client_reviewer(ReviewDB()).get(
        f"/workspaces/{WORKSPACE_ID}/review/{chunk_id}"
    )
    assert response.status_code == 404


def test_get_review_queue_batches_counts_without_per_chunk_queries() -> None:
    db = ReviewDB()
    source_id = str(uuid4())
    chunk_ids = [str(uuid4()) for _ in range(4)]
    db.rows["sources"].append({"id": source_id, "original_filename": "menu.pdf"})
    for i, chunk_id in enumerate(chunk_ids):
        db.rows["chunks"].append({
            "id": chunk_id,
            "workspace_id": WORKSPACE_ID,
            "source_id": source_id,
            "chunk_index": i,
            "content": f"chunk {i}",
            "created_at": f"2024-01-0{i + 1}T10:00:00+00:00",
        })
        db.rows["extracted_facts"].extend([
            {
                "id": str(uuid4()),
                "workspace_id": WORKSPACE_ID,
                "chunk_id": chunk_id,
                "source_id": source_id,
                "fact_type": "service_price",
                "status": "extracted",
                "created_at": f"2024-01-0{i + 1}T10:00:00+00:00",
            },
            {
                "id": str(uuid4()),
                "workspace_id": WORKSPACE_ID,
                "chunk_id": chunk_id,
                "source_id": source_id,
                "fact_type": "contact_info",
                "status": "published",
                "created_at": f"2024-01-0{i + 1}T11:00:00+00:00",
            },
        ])
        db.rows["business_rules"].append({
            "id": str(uuid4()),
            "workspace_id": WORKSPACE_ID,
            "chunk_id": chunk_id,
            "source_id": source_id,
            "rule_type": "discount_rule",
            "status": "published",
        })
        db.rows["unknown_facts_queue"].append({
            "id": str(uuid4()),
            "workspace_id": WORKSPACE_ID,
            "chunk_id": chunk_id,
            "status": "open",
        })

    result = review_service.get_review_queue(
        db,
        workspace_id=WORKSPACE_ID,
        page=2,
        per_page=2,
        fact_type="service_price",
    )

    assert [item["chunk_id"] for item in result["items"]] == chunk_ids[2:4]
    assert result["total"] == 4
    assert all(item["facts_total"] == 2 for item in result["items"])
    assert all(item["rules_total"] == 1 for item in result["items"])
    assert all(item["unknown_total"] == 1 for item in result["items"])
    assert ("extracted_facts", "range", 2, 3) in db.operations
    assert db.executed_tables.count("extracted_facts") <= 2
    assert db.executed_tables.count("business_rules") <= 1
    assert db.executed_tables.count("unknown_facts_queue") <= 1


# ── Approve fact ──────────────────────────────────────────────────────────────

def test_approve_fact_returns_approved_action_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["resource_id"] == fact_id
    assert body["resource_type"] == "extracted_fact"


def test_approve_fact_calls_rpc_with_correct_args(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve",
        json={"note": "looks good"},
    )

    rpc_names = [n for n, _ in db.rpc_calls]
    assert "approve_fact" in rpc_names
    rpc_payload = next(p for n, p in db.rpc_calls if n == "approve_fact")
    assert rpc_payload["target_fact_id"] == fact_id
    assert rpc_payload["reason"] == "looks good"
    assert rpc_payload["actor_user_id"] == USER_ID


def test_approve_fact_emits_structured_review_agent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)
    spy = _SpyLogger()
    monkeypatch.setattr(review_service, "logger", spy)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert spy.infos == [(
        "review-agent.review.approve.succeeded",
        {
            "agent": "review-agent",
            "stage": "review",
            "action": "approve",
            "outcome": "succeeded",
            "workspace_id": WORKSPACE_ID,
            "resource_type": "extracted_fact",
            "resource_id": fact_id,
            "actor_user_id": USER_ID,
        },
    )]


def test_approve_already_approved_fact_returns_200_without_calling_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert not any(n == "approve_fact" for n, _ in db.rpc_calls)


def test_approve_already_approved_fact_emits_skipped_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")
    spy = _SpyLogger()
    monkeypatch.setattr(review_service, "logger", spy)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert spy.infos[0][1]["outcome"] == "skipped"
    assert spy.infos[0][1]["resource_id"] == fact_id


def test_approve_fact_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, workspace_id="other_ws")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert response.status_code == 404


def test_approve_rule_returns_business_rule_resource_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/approve", json={}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resource_type"] == "business_rule"
    assert body["status"] == "approved"


def test_approve_already_approved_rule_returns_200_without_calling_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, status="approved")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/approve", json={}
    )

    assert response.status_code == 200
    assert not any(n == "approve_rule" for n, _ in db.rpc_calls)


# ── Reject fact ───────────────────────────────────────────────────────────────

def test_reject_fact_without_reason_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = _client_reviewer(ReviewDB()).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{str(uuid4())}/reject", json={}
    )
    assert response.status_code == 422


def test_reject_fact_returns_rejected_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/reject",
        json={"reason": "incorrect data"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_reject_fact_calls_rpc_reject_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/reject",
        json={"reason": "wrong value"},
    )

    assert any(n == "reject_fact" for n, _ in db.rpc_calls)


def test_reject_published_fact_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="published")
    db.rpc_raise_for["reject_fact"] = "invalid_fact_status_for_rejection: published"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/reject",
        json={"reason": "wrong"},
    )

    assert response.status_code == 409


def test_publish_fact_with_open_contradiction_returns_specific_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")
    db.rpc_raise_for["publish_fact"] = "fact_has_open_contradiction"

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "fact_has_open_contradiction"


def test_publish_fact_invalid_status_returns_specific_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="extracted")
    db.rpc_raise_for["publish_fact"] = "invalid_fact_status_for_publish: extracted"

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_fact_status_for_publish"


def test_reject_fact_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, workspace_id="other_ws")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/reject",
        json={"reason": "test"},
    )

    assert response.status_code == 404


def test_reject_rule_with_reason_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/reject",
        json={"reason": "policy changed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["resource_type"] == "business_rule"


def test_reject_rule_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, workspace_id="other_ws")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/reject",
        json={"reason": "test"},
    )

    assert response.status_code == 404


# ── Edit fact ─────────────────────────────────────────────────────────────────

def test_edit_fact_valid_content_returns_superseded(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    new_fact_id = str(uuid4())
    db.rpc_return = new_fact_id
    _add_fact(db, fact_id, fact_type="service_price")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "superseded"
    assert body["resource_id"] == new_fact_id
    assert body["resource_type"] == "extracted_fact"


def test_edit_fact_calls_pre_normalize_before_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_fact(db, fact_id, fact_type="service_price")

    normalize_calls: list[tuple[str, dict]] = []

    import normalizers.pre_extract as _pre_mod  # noqa: PLC0415
    original = _pre_mod.pre_normalize

    def _tracking(fact_type: str, raw: dict) -> dict:
        normalize_calls.append((fact_type, raw))
        return original(fact_type, raw)

    monkeypatch.setattr(_pre_mod, "pre_normalize", _tracking)
    monkeypatch.setattr("context_builder.services.review_service.pre_normalize", _tracking)

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    assert len(normalize_calls) >= 1
    assert normalize_calls[0][0] == "service_price"


def test_edit_fact_invalid_content_returns_422_before_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, fact_type="service_price")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": {"wrong_field": "value"}},
    )

    assert response.status_code == 422
    assert not any(n == "create_fact_version" for n, _ in db.rpc_calls)


def test_edit_fact_calls_create_fact_version_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_fact(db, fact_id, fact_type="service_price")

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    rpc_names = [n for n, _ in db.rpc_calls]
    assert "create_fact_version" in rpc_names
    rpc_payload = next(p for n, p in db.rpc_calls if n == "create_fact_version")
    assert rpc_payload["old_fact_id"] == fact_id
    assert "new_content" in rpc_payload
    assert "new_normalized_content" in rpc_payload
    assert rpc_payload["actor_user_id"] == USER_ID


def test_edit_already_superseded_fact_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, fact_type="service_price")
    db.rpc_raise_for["create_fact_version"] = "fact_already_superseded: other-id"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    assert response.status_code == 409


def test_edit_fact_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, workspace_id="other_ws", fact_type="service_price")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    assert response.status_code == 404


# ── Edit rule ─────────────────────────────────────────────────────────────────

def test_edit_discount_rule_validates_with_nested_condition_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_rule(db, rule_id, rule_type="discount_rule")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/edit",
        json={
            "condition": {"payment_method": "pix"},
            "action": {"discount_percentage": 10.0},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "superseded"
    assert response.json()["resource_type"] == "business_rule"


def test_edit_cancellation_policy_validates_with_flat_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_rule(db, rule_id, rule_type="cancellation_policy")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/edit",
        json={
            "condition": {"notice_required_hours": 24.0},
            "action": {"penalty_percentage": 50.0},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "superseded"


def test_edit_rule_invalid_payload_returns_422_before_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, rule_type="discount_rule")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/edit",
        json={"condition": {"bad": "data"}, "action": {"also": "bad"}},
    )

    assert response.status_code == 422
    assert not any(n == "create_rule_version" for n, _ in db.rpc_calls)


def test_edit_rule_calls_create_rule_version_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    db.rpc_return = str(uuid4())
    _add_rule(db, rule_id, rule_type="discount_rule")

    _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/edit",
        json={
            "condition": {"payment_method": "credit"},
            "action": {"discount_percentage": 5.0},
        },
    )

    assert any(n == "create_rule_version" for n, _ in db.rpc_calls)


def test_edit_already_superseded_rule_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, rule_type="discount_rule")
    db.rpc_raise_for["create_rule_version"] = "rule_already_superseded: other-id"

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/edit",
        json={
            "condition": {"payment_method": "pix"},
            "action": {"discount_percentage": 10.0},
        },
    )

    assert response.status_code == 409


# ── ActionResponse shape ──────────────────────────────────────────────────────

def test_action_response_has_resource_id_and_resource_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    body = response.json()
    assert "resource_id" in body
    assert "resource_type" in body
    assert "status" in body


def test_approve_resource_type_is_extracted_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id)

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/approve", json={}
    )

    assert response.json()["resource_type"] == "extracted_fact"


def test_edit_fact_resource_id_is_new_fact_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    new_id = str(uuid4())
    db.rpc_return = new_id
    _add_fact(db, fact_id, fact_type="service_price")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/edit",
        json={"content": _VALID_PRICE},
    )

    assert response.json()["resource_id"] == new_id


def test_publish_fact_returns_published_action_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    assert body["resource_id"] == fact_id
    assert body["resource_type"] == "extracted_fact"


def test_reviewer_cannot_publish_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"
    assert not any(name == "publish_fact" for name, _ in db.rpc_calls)


def test_publish_fact_calls_rpc_with_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="approved")

    _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    rpc_payload = next(p for n, p in db.rpc_calls if n == "publish_fact")
    assert rpc_payload["target_fact_id"] == fact_id
    assert rpc_payload["actor_user_id"] == USER_ID


def test_publish_already_published_fact_returns_200_without_calling_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, status="published")

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert not any(n == "publish_fact" for n, _ in db.rpc_calls)


def test_publish_fact_from_other_workspace_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    fact_id = str(uuid4())
    _add_fact(db, fact_id, workspace_id="other_ws", status="approved")

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/facts/{fact_id}/publish"
    )

    assert response.status_code == 404


def test_publish_rule_returns_published_action_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, status="approved")

    response = _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/publish"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    assert body["resource_id"] == rule_id
    assert body["resource_type"] == "business_rule"


def test_reviewer_cannot_publish_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, status="approved")

    response = _client_reviewer(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/publish"
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"
    assert not any(name == "publish_rule" for name, _ in db.rpc_calls)


def test_publish_rule_calls_rpc_with_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ReviewDB()
    rule_id = str(uuid4())
    _add_rule(db, rule_id, status="approved")

    _client_manager(db).post(
        f"/workspaces/{WORKSPACE_ID}/review/rules/{rule_id}/publish"
    )

    rpc_payload = next(p for n, p in db.rpc_calls if n == "publish_rule")
    assert rpc_payload["target_rule_id"] == rule_id
    assert rpc_payload["actor_user_id"] == USER_ID
