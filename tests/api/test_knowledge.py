"""Tests for GET /workspaces/{workspace_id}/knowledge."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from context_builder.config import get_settings
from context_builder.dependencies import (
    get_current_user,
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.main import create_app
from fastapi.testclient import TestClient

WORKSPACE_ID = "ws-knowledge-001"
OTHER_WORKSPACE = "ws-other-999"
USER_ID = str(uuid4())

_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "u@test.com"},
    "role": "staff",
    "workspace_id": WORKSPACE_ID,
}


# ── Stubs ─────────────────────────────────────────────────────────────────────


class Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


class KnowledgeQuery:
    def __init__(self, db: KnowledgeDB, table_name: str, rows: list[dict[str, Any]]) -> None:
        self._db = db
        self._table_name = table_name
        self._rows = rows
        self._filters: dict[str, Any] = {}
        self._orders: list[tuple[str, bool]] = []
        self._range: tuple[int, int] | None = None
        self._count_requested = False

    def select(self, _fields: str, **kwargs: Any) -> KnowledgeQuery:
        self._count_requested = kwargs.get("count") == "exact"
        return self

    def eq(self, field: str, value: Any) -> KnowledgeQuery:
        self._filters[field] = value
        return self

    def order(self, field: str, **kw: Any) -> KnowledgeQuery:
        self._orders.append((field, bool(kw.get("desc"))))
        self._db.operations.append((self._table_name, "order", field, kw))
        return self

    def range(self, start: int, end: int) -> KnowledgeQuery:
        self._range = (start, end)
        self._db.operations.append((self._table_name, "range", start, end))
        return self

    def execute(self) -> Result:
        self._db.operations.append((self._table_name, "execute", dict(self._filters)))
        rows = list(self._rows)
        for field, value in self._filters.items():
            rows = [r for r in rows if r.get(field) == value]
        for field, desc in reversed(self._orders):
            rows.sort(key=lambda r: r.get(field) or "", reverse=desc)
        count = len(rows) if self._count_requested else None
        if self._range:
            start, end = self._range
            rows = rows[start : end + 1]
        return Result(rows, count=count)


class KnowledgeDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "published_facts": [],
            "published_rules": [],
        }
        self.operations: list[tuple[Any, ...]] = []

    def table(self, name: str) -> KnowledgeQuery:
        return KnowledgeQuery(self, name, self.rows.get(name, []))


# ── Helpers ────────────────────────────────────────────────────────────────────


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()


def _client(db: KnowledgeDB) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID, "email": "u@test.com"}
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: _MEMBERSHIP
    return TestClient(app)


def _fact(
    *,
    fact_id: str | None = None,
    workspace_id: str = WORKSPACE_ID,
    fact_type: str = "service_price",
    source_id: str | None = None,
    published_at: str = "2024-01-01T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": fact_id or str(uuid4()),
        "workspace_id": workspace_id,
        "fact_type": fact_type,
        "schema_version": "1.0.0",
        "normalized_content": {"price": "50.00", "currency": "BRL"},
        "confidence": 0.95,
        "source_id": source_id or str(uuid4()),
        "chunk_id": str(uuid4()),
        "published_at": published_at,
        "reviewed_by": None,
    }


def _rule(
    *,
    rule_id: str | None = None,
    workspace_id: str = WORKSPACE_ID,
    rule_type: str = "discount_rule",
    source_id: str | None = None,
    published_at: str = "2024-01-01T11:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": rule_id or str(uuid4()),
        "workspace_id": workspace_id,
        "rule_type": rule_type,
        "schema_version": "1.0.0",
        "condition": {"min_items": 3},
        "action": {"discount_percent": 10},
        "priority": 100,
        "confidence": 0.90,
        "source_id": source_id or str(uuid4()),
        "chunk_id": str(uuid4()),
        "published_at": published_at,
        "reviewed_by": None,
    }


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_no_bearer_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = TestClient(create_app()).get(f"/workspaces/{WORKSPACE_ID}/knowledge")
    assert response.status_code == 401


# ── Empty state ────────────────────────────────────────────────────────────────


def test_empty_workspace_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["facts_count"] == 0
    assert body["rules_count"] == 0
    assert body["pages"] == 0


# ── record_type filter ─────────────────────────────────────────────────────────


def test_record_type_all_returns_facts_and_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact())
    db.rows["published_rules"].append(_rule())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=all")

    assert response.status_code == 200
    body = response.json()
    kinds = {item["kind"] for item in body["items"]}
    assert kinds == {"fact", "rule"}
    assert body["facts_count"] == 1
    assert body["rules_count"] == 1
    assert body["total"] == 2


def test_record_type_facts_returns_only_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact())
    db.rows["published_rules"].append(_rule())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=facts")

    assert response.status_code == 200
    body = response.json()
    assert all(item["kind"] == "fact" for item in body["items"])
    assert body["facts_count"] == 1
    assert body["rules_count"] == 0


def test_record_type_rules_returns_only_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact())
    db.rows["published_rules"].append(_rule())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=rules")

    assert response.status_code == 200
    body = response.json()
    assert all(item["kind"] == "rule" for item in body["items"])
    assert body["facts_count"] == 0
    assert body["rules_count"] == 1


def test_invalid_record_type_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=invalid")
    assert response.status_code == 422


# ── kind_filter ────────────────────────────────────────────────────────────────


def test_kind_filter_returns_only_matching_fact_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(fact_type="service_price"))
    db.rows["published_facts"].append(_fact(fact_type="business_hours"))

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?kind_filter=service_price"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts_count"] == 1
    assert body["items"][0]["fact_type"] == "service_price"


def test_kind_filter_returns_only_matching_rule_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_rules"].append(_rule(rule_type="discount_rule"))
    db.rows["published_rules"].append(_rule(rule_type="cancellation_policy"))

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=rules&kind_filter=discount_rule"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rules_count"] == 1
    assert body["items"][0]["rule_type"] == "discount_rule"


def test_kind_filter_no_match_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(fact_type="service_price"))

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?kind_filter=contact_info"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


# ── source_id filter ──────────────────────────────────────────────────────────


def test_source_id_filter_returns_only_records_from_that_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    target_source = str(uuid4())
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(source_id=target_source))
    db.rows["published_facts"].append(_fact(source_id=str(uuid4())))

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?source_id={target_source}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts_count"] == 1
    assert body["items"][0]["source_id"] == target_source


def test_source_id_filter_applies_to_both_facts_and_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    target_source = str(uuid4())
    other_source = str(uuid4())
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(source_id=target_source))
    db.rows["published_facts"].append(_fact(source_id=other_source))
    db.rows["published_rules"].append(_rule(source_id=target_source))
    db.rows["published_rules"].append(_rule(source_id=other_source))

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?source_id={target_source}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts_count"] == 1
    assert body["rules_count"] == 1
    assert body["total"] == 2


# ── Pagination ─────────────────────────────────────────────────────────────────


def test_per_page_limits_items_on_page(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    for _ in range(5):
        db.rows["published_facts"].append(_fact())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?per_page=2&page=1")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["pages"] == 3
    assert body["facts_count"] == 5  # full count, not just page items


def test_page2_returns_second_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    for i in range(4):
        db.rows["published_facts"].append(
            _fact(published_at=f"2024-01-0{i + 1}T10:00:00+00:00")
        )

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?per_page=2&page=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["page"] == 2


def test_page_beyond_last_returns_empty_items(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?per_page=10&page=99")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 1  # full count still reported


def test_facts_pagination_uses_database_order_and_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    for i in range(5):
        db.rows["published_facts"].append(
            _fact(
                fact_id=f"00000000-0000-0000-0000-00000000000{i}",
                published_at=f"2024-01-0{i + 1}T10:00:00+00:00",
            )
        )

    response = _client(db).get(
        f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=facts&per_page=2&page=2"
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["published_at"] for item in body["items"]] == [
        "2024-01-03T10:00:00Z",
        "2024-01-02T10:00:00Z",
    ]
    assert body["total"] == 5
    assert body["facts_count"] == 5
    assert ("published_facts", "range", 2, 3) in db.operations
    assert any(
        op[0] == "published_facts"
        and op[1] == "order"
        and op[2] == "published_at"
        and op[3].get("desc") is True
        for op in db.operations
    )


# ── Cross-tenant guard ────────────────────────────────────────────────────────


def test_facts_from_other_workspace_are_not_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(workspace_id=WORKSPACE_ID))
    db.rows["published_facts"].append(_fact(workspace_id=OTHER_WORKSPACE))

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge")

    assert response.status_code == 200
    body = response.json()
    assert body["facts_count"] == 1
    for item in body["items"]:
        assert item.get("workspace_id") != OTHER_WORKSPACE


def test_rules_from_other_workspace_are_not_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_rules"].append(_rule(workspace_id=WORKSPACE_ID))
    db.rows["published_rules"].append(_rule(workspace_id=OTHER_WORKSPACE))

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge")

    assert response.status_code == 200
    body = response.json()
    assert body["rules_count"] == 1


def test_workspace_isolation_across_facts_and_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    db.rows["published_facts"].append(_fact(workspace_id=WORKSPACE_ID))
    db.rows["published_facts"].append(_fact(workspace_id=OTHER_WORKSPACE))
    db.rows["published_rules"].append(_rule(workspace_id=WORKSPACE_ID))
    db.rows["published_rules"].append(_rule(workspace_id=OTHER_WORKSPACE))

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge")

    assert response.status_code == 200
    body = response.json()
    assert body["facts_count"] == 1
    assert body["rules_count"] == 1
    assert body["total"] == 2


# ── Response shape ─────────────────────────────────────────────────────────────


def test_fact_item_has_kind_and_fact_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    fact_id = str(uuid4())
    db.rows["published_facts"].append(_fact(fact_id=fact_id, fact_type="contact_info"))

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=facts")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["kind"] == "fact"
    assert item["fact_type"] == "contact_info"
    assert "normalized_content" in item
    assert "id" in item
    assert "condition" not in item
    assert "action" not in item


def test_rule_item_has_kind_and_rule_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    rule_id = str(uuid4())
    db.rows["published_rules"].append(
        _rule(rule_id=rule_id, rule_type="cancellation_policy")
    )

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge?record_type=rules")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["kind"] == "rule"
    assert item["rule_type"] == "cancellation_policy"
    assert "condition" in item
    assert "action" in item
    assert "priority" in item
    assert "normalized_content" not in item
    assert "fact_type" not in item


def test_response_envelope_fields_are_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = KnowledgeDB()
    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/knowledge")
    assert response.status_code == 200
    body = response.json()
    for key in ("items", "total", "page", "per_page", "pages", "facts_count", "rules_count"):
        assert key in body, f"Missing key: {key}"
