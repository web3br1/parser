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

WORKSPACE_ID = "ws_1"
USER_ID = "user_1"

_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "u@test.com"},
    "role": "staff",
    "workspace_id": WORKSPACE_ID,
}


class QueryDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "published_facts": [],
            "published_rules": [],
            "published_sources": [],
            "evidence_spans": [],
            "extracted_facts": [],
            "business_rules": [],
            "unknown_facts_queue": [],
            "contradictions": [],
            "query_audits": [],
            "audit_logs": [],
            "token_usage_log": [],
        }
        self.inserted: dict[str, list[dict[str, Any]]] = {
            "query_audits": [],
            "audit_logs": [],
            "token_usage_log": [],
        }
        self.selected_tables: list[str] = []
        self.filters: list[tuple[str, str, str, Any]] = []
        self.return_insert_data = True

    @property
    def published_facts(self) -> list[dict[str, Any]]:
        return self.rows["published_facts"]

    @property
    def published_rules(self) -> list[dict[str, Any]]:
        return self.rows["published_rules"]

    @property
    def published_sources(self) -> list[dict[str, Any]]:
        return self.rows["published_sources"]

    @property
    def evidence_spans(self) -> list[dict[str, Any]]:
        return self.rows["evidence_spans"]

    @property
    def extracted_facts(self) -> list[dict[str, Any]]:
        return self.rows["extracted_facts"]

    @property
    def business_rules(self) -> list[dict[str, Any]]:
        return self.rows["business_rules"]

    @property
    def unknown_facts_queue(self) -> list[dict[str, Any]]:
        return self.rows["unknown_facts_queue"]

    @property
    def contradictions(self) -> list[dict[str, Any]]:
        return self.rows["contradictions"]

    @property
    def selected_tables_for_answer(self) -> list[str]:
        return [
            table
            for table in self.selected_tables
            if table not in {"query_audits", "audit_logs"}
        ]

    def table(self, name: str) -> QueryTable:
        return QueryTable(self, name)


class QueryResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class QueryTable:
    def __init__(self, db: QueryDB, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self._filters: list[tuple[str, str, Any]] = []
        self._insert_rows: list[dict[str, Any]] | None = None
        self._single = False
        self._limit: int | None = None

    def select(self, *_columns: str) -> QueryTable:
        self.db.selected_tables.append(self.table_name)
        return self

    def insert(self, rows: dict[str, Any] | list[dict[str, Any]]) -> QueryTable:
        if isinstance(rows, dict):
            self._insert_rows = [rows]
        else:
            self._insert_rows = rows
        return self

    def eq(self, column: str, value: Any) -> QueryTable:
        self._filters.append(("eq", column, value))
        self.db.filters.append((self.table_name, "eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> QueryTable:
        self._filters.append(("in", column, values))
        self.db.filters.append((self.table_name, "in", column, values))
        return self

    def limit(self, count: int) -> QueryTable:
        self._limit = count
        self.db.filters.append((self.table_name, "limit", "count", count))
        return self

    def maybe_single(self) -> QueryTable:
        self._single = True
        return self

    def execute(self) -> QueryResult:
        if self._insert_rows is not None:
            inserted = []
            for row in self._insert_rows:
                stored = dict(row)
                stored.setdefault("id", str(uuid4()))
                self.db.rows.setdefault(self.table_name, []).append(stored)
                self.db.inserted.setdefault(self.table_name, []).append(stored)
                inserted.append(stored)
            if not self.db.return_insert_data:
                return QueryResult([])
            return QueryResult(inserted[0] if self._single else inserted)

        rows = list(self.db.rows.get(self.table_name, []))
        for operator, column, value in self._filters:
            if operator == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif operator == "in":
                rows = [row for row in rows if row.get(column) in value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return QueryResult((rows[0] if rows else None) if self._single else rows)


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()


def _client_member(db: Any) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": USER_ID,
        "email": "u@test.com",
    }
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: _MEMBERSHIP
    return TestClient(app)


def _query_service() -> Any:
    try:
        from context_builder.services import query_service
    except ImportError:
        pytest.fail(
            "Expected context_builder.services.query_service with answer_query for "
            "POST /workspaces/{workspace_id}/query",
            pytrace=False,
        )
    return query_service


def _answer_query(db: QueryDB, question: str) -> dict[str, Any]:
    return _query_service().answer_query(
        db,
        workspace_id=WORKSPACE_ID,
        question=question,
        actor_user_id=USER_ID,
        max_output_tokens=None,
        include_evidence=True,
    )


def _published_source(source_id: str = "source_published_1", **overrides: Any) -> dict[str, Any]:
    row = {
        "id": source_id,
        "workspace_id": WORKSPACE_ID,
        "original_filename": "catalogo.pdf",
        "status": "published",
    }
    row.update(overrides)
    return row


def _evidence_span(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "evidence_price_1",
        "workspace_id": WORKSPACE_ID,
        "source_id": "source_published_1",
        "chunk_id": "chunk_published_1",
        "quote": "Corte: R$ 50",
        "page_number": 2,
        "sheet_name": None,
        "row_number": None,
    }
    row.update(overrides)
    return row


def _published_price_fact(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "fact_published_price_1",
        "workspace_id": WORKSPACE_ID,
        "source_id": "source_published_1",
        "chunk_id": "chunk_published_1",
        "evidence_span_id": "evidence_price_1",
        "fact_type": "service_price",
        "content": {"service": "corte", "price": "R$ 50"},
        "normalized_content": {"service": "corte", "price": 50, "currency": "BRL"},
        "confidence": 0.91,
        "status": "published",
    }
    row.update(overrides)
    return row


def _pending_price_fact(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "fact_pending_price_1",
        "workspace_id": WORKSPACE_ID,
        "source_id": "source_pending_1",
        "chunk_id": "chunk_pending_1",
        "fact_type": "service_price",
        "content": {"service": "corte", "price": "R$ 10"},
        "normalized_content": {"service": "corte", "price": 10, "currency": "BRL"},
        "confidence": 0.99,
        "status": "needs_review",
    }
    row.update(overrides)
    return row


def _unknown_price_item(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "unknown_price_1",
        "workspace_id": WORKSPACE_ID,
        "source_id": "source_pending_1",
        "chunk_id": "chunk_pending_1",
        "reason": "unclassified_fact",
        "content": {
            "service": "corte",
            "price": "R$ 10",
            "internal_notes": "aguardando triagem humana",
        },
        "normalized_content": {"service": "corte", "price": 10, "currency": "BRL"},
        "status": "open",
    }
    row.update(overrides)
    return row


def _published_discount_rule(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "rule_published_discount_1",
        "workspace_id": WORKSPACE_ID,
        "source_id": "source_published_rule_1",
        "chunk_id": "chunk_published_rule_1",
        "rule_type": "discount_rule",
        "condition": {"service": "corte", "payment_method": "pix"},
        "action": {"discount": "5%"},
        "confidence": 0.88,
        "status": "published",
    }
    row.update(overrides)
    return row


def _open_contradiction(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "contradiction_open_price_1",
        "workspace_id": WORKSPACE_ID,
        "status": "open",
        "severity": "high",
        "fact_ids": ["fact_published_price_1", "fact_published_price_2"],
        "rule_ids": [],
        "source_ids": ["source_published_1", "source_published_2"],
        "field_path": "normalized_content.price",
    }
    row.update(overrides)
    return row


def _assert_sensitive_keys_absent(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in {"cost", "margin", "internal_notes"}
            _assert_sensitive_keys_absent(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_sensitive_keys_absent(item)


def _assert_sensitive_answer_text_absent(text: str) -> None:
    assert "cost" not in text
    assert "margin" not in text
    assert "internal_notes" not in text
    assert "R$ 20" not in text
    assert "60%" not in text
    assert "nao mencionar em atendimento" not in text
    assert "negociar apenas com gerente" not in text
    assert "apenas se cliente insistir" not in text


def test_post_query_without_bearer_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = TestClient(create_app()).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Quais servicos custam menos de R$ 100?"},
    )
    assert response.status_code == 401


def test_post_query_member_returns_service_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    query_service = _query_service()
    db = QueryDB()
    captured: list[dict[str, Any]] = []
    service_response = {
        "audit_id": str(uuid4()),
        "answer_state": "valid_answer",
        "answer": "Corte custa R$ 50.",
        "confidence": 0.9,
        "used_unvalidated_data": False,
        "facts_used": [],
        "rules_used": [],
        "sources_used": [],
        "evidence": [],
        "missing_data": [],
        "warnings": [],
        "usage": {
            "model_provider": None,
            "model_name": None,
            "model_context_limit_tokens": 128000,
            "context_budget_tokens": 6000,
            "context_pack_tokens_estimated": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
        },
    }

    def _answer_query(db_arg: Any, **kw: Any) -> dict[str, Any]:
        captured.append({"db": db_arg, **kw})
        return service_response

    monkeypatch.setattr(query_service, "answer_query", _answer_query)

    response = _client_member(db).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte?"},
    )

    assert response.status_code == 200
    assert response.json() == service_response
    assert captured == [
        {
            "db": db,
            "workspace_id": WORKSPACE_ID,
            "question": "Qual o preco do corte?",
            "actor_user_id": USER_ID,
            "user_role": "staff",
            "max_output_tokens": None,
            "include_evidence": True,
        },
    ]


def test_post_query_empty_question_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    response = _client_member(QueryDB()).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": ""},
    )
    assert response.status_code == 422


def test_post_query_unsupported_mode_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    response = _client_member(QueryDB()).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte?", "mode": "chat"},
    )
    assert response.status_code == 422


def test_post_query_passes_output_limit_and_evidence_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    query_service = _query_service()
    db = QueryDB()
    captured: list[dict[str, Any]] = []

    def _answer_query(db_arg: Any, **kw: Any) -> dict[str, Any]:
        captured.append({"db": db_arg, **kw})
        return {
            "audit_id": str(uuid4()),
            "answer_state": "not_found",
            "answer": "Nao encontrei essa informacao nas fontes validadas.",
            "confidence": 0.0,
            "used_unvalidated_data": False,
            "facts_used": [],
            "rules_used": [],
            "sources_used": [],
            "evidence": [],
            "missing_data": ["published_data"],
            "warnings": [],
            "usage": {
                "model_provider": None,
                "model_name": None,
                "model_context_limit_tokens": 128000,
                "context_budget_tokens": 6000,
                "context_pack_tokens_estimated": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            },
        }

    monkeypatch.setattr(query_service, "answer_query", _answer_query)

    response = _client_member(db).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={
            "question": "Qual o preco do corte?",
            "max_output_tokens": 123,
            "include_evidence": False,
        },
    )

    assert response.status_code == 200
    assert captured[0]["max_output_tokens"] == 123
    assert captured[0]["include_evidence"] is False


def test_query_no_published_data_returns_not_found_and_audits() -> None:
    db = QueryDB()

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["used_unvalidated_data"] is False
    assert result["facts_used"] == []
    assert result["rules_used"] == []
    assert result["sources_used"] == []
    assert db.selected_tables_for_answer == [
        "published_sources",
        "published_facts",
        "published_rules",
        "extracted_facts",
        "business_rules",
        "unknown_facts_queue",
    ]

    assert len(db.inserted["query_audits"]) == 1
    query_audit = db.inserted["query_audits"][0]
    assert query_audit["workspace_id"] == WORKSPACE_ID
    assert query_audit["user_id"] == USER_ID
    assert query_audit["question"] == "Qual o preco do corte?"
    assert query_audit["answer_state"] == "not_found"
    assert query_audit["used_unvalidated_data"] is False

    assert len(db.inserted["audit_logs"]) == 1
    audit_log = db.inserted["audit_logs"][0]
    assert audit_log["workspace_id"] == WORKSPACE_ID
    assert audit_log["actor_user_id"] == USER_ID
    assert audit_log["action"] == "query.answer"
    assert audit_log["resource_type"] == "query_audit"
    assert audit_log["resource_id"] == query_audit["id"]


def test_query_published_fact_returns_valid_answer_and_uses_published_fact_ids() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.evidence_spans.append(_evidence_span())
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "valid_answer"
    assert result["used_unvalidated_data"] is False
    assert result["facts_used"] == ["fact_published_price_1"]
    assert result["rules_used"] == []
    assert result["sources_used"] == ["source_published_1"]
    assert result["usage"]["input_tokens"] >= result["usage"]["context_pack_tokens_estimated"]
    assert result["usage"]["output_tokens"] > 0
    assert result["evidence"] == [
        {
            "source_id": "source_published_1",
            "source_name": "catalogo.pdf",
            "evidence_span_id": "evidence_price_1",
            "quote": "Corte: R$ 50",
            "page_number": 2,
            "sheet_name": None,
            "row_number": None,
            "chunk_id": "chunk_published_1",
            "fact_id": "fact_published_price_1",
            "rule_id": None,
        },
    ]
    assert "R$ 50" in result["answer"]
    assert db.selected_tables_for_answer == [
        "published_sources",
        "published_facts",
        "published_rules",
        "contradictions",
        "evidence_spans",
    ]
    assert db.inserted["query_audits"][0]["answer_state"] == "valid_answer"
    assert db.inserted["query_audits"][0]["facts_used"] == ["fact_published_price_1"]
    assert db.inserted["query_audits"][0]["sources_used"] == ["source_published_1"]
    assert result["audit_id"] == db.inserted["query_audits"][0]["id"]
    assert db.inserted["audit_logs"][0]["metadata"][
        "context_pack_hash"
    ] == _query_service()._hash_payload(
        {
            "workspace_id": WORKSPACE_ID,
            "question": "Qual o preco do corte?",
            "facts": [_published_price_fact()],
            "rules": [],
            "sources": [_published_source()],
            "evidence": result["evidence"],
        }
    )
    assert db.inserted["audit_logs"][0]["metadata"]["candidate_count"] == 1
    assert db.inserted["audit_logs"][0]["metadata"]["selected_count"] == 1
    assert (
        db.inserted["audit_logs"][0]["metadata"]["ranking_strategy"]
        == "deterministic_v1"
    )


def test_query_counts_and_limits_response_tokens() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.published_facts.append(
        _published_price_fact(
            content={
                "service": "corte",
                "price": "R$ 50",
                "description": "descricao publica detalhada " * 20,
            },
            normalized_content={
                "service": "corte",
                "price": 50,
                "currency": "BRL",
                "description": "descricao publica detalhada " * 20,
            },
        )
    )

    result = _query_service().answer_query(
        db,
        workspace_id=WORKSPACE_ID,
        question="Qual o preco do corte?",
        actor_user_id=USER_ID,
        max_output_tokens=8,
        include_evidence=False,
    )

    assert result["usage"]["output_tokens"] <= 8
    assert "output_truncated" in result["warnings"]
    assert result["answer"].endswith("...")
    assert db.inserted["query_audits"][0]["token_output"] == result["usage"]["output_tokens"]
    assert db.inserted["audit_logs"][0]["metadata"]["usage_is_estimated"] is True


def test_query_evidence_reads_only_used_spans_and_redacts_sensitive_staff_quotes() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.evidence_spans.append(
        _evidence_span(quote="Corte publico R$ 50; cost R$ 20; internal_notes segredo")
    )
    db.evidence_spans.append(
        _evidence_span(
            id="evidence_unused_secret",
            source_id="source_published_1",
            chunk_id="chunk_unused_secret",
            quote="internal_notes nunca retornar",
        )
    )
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "valid_answer"
    assert result["evidence"][0]["evidence_span_id"] == "evidence_price_1"
    assert result["evidence"][0]["quote"] is None
    assert "internal_notes" not in str(result)
    assert ("evidence_spans", "in", "id", ["evidence_price_1"]) in db.filters


def test_query_pending_related_data_returns_needs_human_validation_without_leaking_pending_content() -> None:
    db = QueryDB()
    db.extracted_facts.append(_pending_price_fact())
    db.business_rules.append(
        {
            "id": "rule_pending_discount_1",
            "workspace_id": WORKSPACE_ID,
            "source_id": "source_pending_rule_1",
            "chunk_id": "chunk_pending_rule_1",
            "rule_type": "discount_rule",
            "condition": {"service": "corte"},
            "action": {"discount": "90%"},
            "status": "needs_review",
        },
    )

    result = _answer_query(db, "Qual o preco do corte e tem desconto?")

    assert result["answer_state"] == "needs_human_validation"
    assert result["answer"] == (
        "Existe informacao relacionada, mas ela ainda nao foi validada por "
        "revisao humana."
    )
    assert result["used_unvalidated_data"] is False
    assert result["facts_used"] == []
    assert result["rules_used"] == []
    assert result["sources_used"] == []
    assert result["evidence"] == []
    assert result["missing_data"] == ["human_validation"]
    assert "R$ 10" not in result["answer"]
    assert "90%" not in result["answer"]
    assert db.selected_tables_for_answer == [
        "published_sources",
        "published_facts",
        "published_rules",
        "extracted_facts",
        "business_rules",
    ]
    assert db.inserted["query_audits"][0]["answer_state"] == "needs_human_validation"
    assert db.inserted["query_audits"][0]["used_unvalidated_data"] is False
    assert "R$ 10" not in str(db.inserted["query_audits"][0])
    assert "90%" not in str(db.inserted["query_audits"][0])


def test_query_unknown_only_related_data_returns_needs_human_validation_without_leaking_unknown_content() -> None:
    db = QueryDB()
    db.unknown_facts_queue.append(_unknown_price_item())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "needs_human_validation"
    assert result["used_unvalidated_data"] is False
    assert result["facts_used"] == []
    assert result["rules_used"] == []
    assert result["sources_used"] == []
    assert result["evidence"] == []
    assert result["missing_data"] == ["human_validation"]
    assert "R$ 10" not in str(result)
    assert "aguardando triagem humana" not in str(result)
    assert db.selected_tables_for_answer == [
        "published_sources",
        "published_facts",
        "published_rules",
        "extracted_facts",
        "business_rules",
        "unknown_facts_queue",
    ]
    assert db.inserted["query_audits"][0]["answer_state"] == "needs_human_validation"
    assert "R$ 10" not in str(db.inserted["query_audits"][0])
    assert "aguardando triagem humana" not in str(db.inserted["query_audits"][0])


def test_query_open_contradiction_returns_conflicting_sources_without_used_items() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_published_1"),
            _published_source("source_published_2"),
        ]
    )
    db.published_facts.extend(
        [
            _published_price_fact(),
            _published_price_fact(
                id="fact_published_price_2",
                source_id="source_published_2",
                chunk_id="chunk_published_2",
                content={"service": "corte", "price": "R$ 70"},
                normalized_content={"service": "corte", "price": 70, "currency": "BRL"},
            ),
        ]
    )
    db.contradictions.append(_open_contradiction())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "conflicting_sources"
    assert result["answer"] == (
        "Encontrei fontes publicadas conflitantes. E necessario resolver o "
        "conflito antes de responder."
    )
    assert result["confidence"] == 0.0
    assert result["facts_used"] == []
    assert result["rules_used"] == []
    assert result["sources_used"] == ["source_published_1", "source_published_2"]
    assert result["evidence"] == []
    assert result["warnings"] == ["conflict_requires_review"]
    assert db.selected_tables_for_answer == [
        "published_sources",
        "published_facts",
        "published_rules",
        "contradictions",
    ]
    assert db.inserted["query_audits"][0]["answer_state"] == "conflicting_sources"
    assert db.inserted["query_audits"][0]["facts_used"] == []
    assert db.inserted["query_audits"][0]["rules_used"] == []


def test_query_needs_review_contradiction_returns_conflicting_sources() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_published_1"),
            _published_source("source_published_2"),
        ]
    )
    db.published_facts.extend(
        [
            _published_price_fact(),
            _published_price_fact(
                id="fact_published_price_2",
                source_id="source_published_2",
                chunk_id="chunk_published_2",
                content={"service": "corte", "price": "R$ 70"},
                normalized_content={"service": "corte", "price": 70, "currency": "BRL"},
            ),
        ]
    )
    db.contradictions.append(_open_contradiction(status="needs_review"))

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "conflicting_sources"
    assert result["facts_used"] == []
    assert result["rules_used"] == []
    assert result["sources_used"] == ["source_published_1", "source_published_2"]
    assert result["warnings"] == ["conflict_requires_review"]


def test_query_open_contradiction_blocks_single_relevant_candidate() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.published_facts.append(_published_price_fact())
    db.contradictions.append(
        _open_contradiction(
            fact_ids=["fact_published_price_1", "fact_missing_from_view"],
            source_ids=["source_published_1", "source_archived_price"],
        )
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "conflicting_sources"
    assert result["facts_used"] == []
    assert result["sources_used"] == ["source_published_1", "source_archived_price"]


def test_query_conflict_context_hash_includes_contradiction_payload() -> None:
    db_a = QueryDB()
    db_a.published_sources.append(_published_source())
    db_a.published_facts.append(_published_price_fact())
    db_a.contradictions.append(
        _open_contradiction(
            id="contradiction_a",
            fact_ids=["fact_published_price_1"],
            source_ids=["source_published_1", "source_archived_a"],
            field_path="normalized_content.price",
        )
    )

    db_b = QueryDB()
    db_b.published_sources.append(_published_source())
    db_b.published_facts.append(_published_price_fact())
    db_b.contradictions.append(
        _open_contradiction(
            id="contradiction_b",
            fact_ids=["fact_published_price_1"],
            source_ids=["source_published_1", "source_archived_b"],
            field_path="normalized_content.currency",
        )
    )

    _answer_query(db_a, "Qual o preco do corte?")
    _answer_query(db_b, "Qual o preco do corte?")

    assert (
        db_a.inserted["audit_logs"][0]["metadata"]["context_pack_hash"]
        != db_b.inserted["audit_logs"][0]["metadata"]["context_pack_hash"]
    )


def test_query_staff_response_and_audit_redact_sensitive_answer_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_published_1"),
            _published_source("source_published_rule_1"),
        ]
    )
    db.published_facts.append(
        _published_price_fact(
            content={
                "name": "corte",
                "public_price": "R$ 50",
                "cost": "R$ 20",
                "margin": "60%",
                "internal_notes": "nao mencionar em atendimento",
            },
            normalized_content={
                "name": "corte",
                "public_price": 50,
                "currency": "BRL",
                "cost": 20,
                "margin": 0.6,
                "internal_notes": "negociar apenas com gerente",
            },
        )
    )
    db.published_rules.append(
        _published_discount_rule(
            action={
                "discount": "5%",
                "cost": "R$ 20",
                "margin": "55%",
                "internal_notes": "apenas se cliente insistir",
            }
        )
    )

    response = _client_member(db).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte e desconto no Pix?"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["answer_state"] == "valid_answer"
    assert "corte" in result["answer"]
    assert "R$ 50" in result["answer"]
    _assert_sensitive_keys_absent(result)
    _assert_sensitive_keys_absent(db.inserted["query_audits"][0])
    _assert_sensitive_keys_absent(db.inserted["audit_logs"][0]["metadata"])
    _assert_sensitive_answer_text_absent(result["answer"])
    _assert_sensitive_answer_text_absent(db.inserted["query_audits"][0]["answer"])


def test_query_manager_response_and_audit_redact_sensitive_answer_fields() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_published_1"),
            _published_source("source_published_rule_1"),
        ]
    )
    db.published_facts.append(
        _published_price_fact(
            content={
                "name": "corte",
                "public_price": "R$ 50",
                "cost": "R$ 20",
                "margin": "60%",
                "internal_notes": "nao mencionar em atendimento",
            },
            normalized_content={
                "name": "corte",
                "public_price": 50,
                "currency": "BRL",
                "cost": 20,
                "margin": 0.6,
                "internal_notes": "negociar apenas com gerente",
            },
        )
    )
    db.published_rules.append(
        _published_discount_rule(
            action={
                "discount": "5%",
                "cost": "R$ 20",
                "margin": "55%",
                "internal_notes": "apenas se cliente insistir",
            }
        )
    )

    result = _query_service().answer_query(
        db,
        workspace_id=WORKSPACE_ID,
        question="Qual o preco do corte e desconto no Pix?",
        actor_user_id=USER_ID,
        user_role="manager",
        max_output_tokens=None,
        include_evidence=True,
    )

    assert result["answer_state"] == "valid_answer"
    assert "R$ 50" in result["answer"]
    _assert_sensitive_keys_absent(result)
    _assert_sensitive_keys_absent(db.inserted["query_audits"][0])
    _assert_sensitive_keys_absent(db.inserted["audit_logs"][0]["metadata"])
    _assert_sensitive_answer_text_absent(result["answer"])
    _assert_sensitive_answer_text_absent(db.inserted["query_audits"][0]["answer"])


def test_query_many_published_facts_respect_context_budget_tokens_in_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_CONTEXT_BUDGET_TOKENS", "120")
    get_settings.cache_clear()
    db = QueryDB()
    for index in range(30):
        db.published_sources.append(_published_source(f"source_published_{index:02d}"))
        db.published_facts.append(
            _published_price_fact(
                id=f"fact_published_price_{index:02d}",
                source_id=f"source_published_{index:02d}",
                chunk_id=f"chunk_published_{index:02d}",
                content={
                    "service": f"servico {index:02d}",
                    "price": f"R$ {50 + index}",
                    "description": "pacote detalhado " * 20,
                },
                normalized_content={
                    "service": f"servico {index:02d}",
                    "price": 50 + index,
                    "currency": "BRL",
                    "description": "pacote detalhado " * 20,
                },
            )
        )

    result = _answer_query(db, "Precos servicos")

    assert result["usage"]["context_budget_tokens"] == 120
    assert (
        result["usage"]["context_pack_tokens_estimated"]
        <= result["usage"]["context_budget_tokens"]
    )
    assert len(result["facts_used"]) < 30
    assert db.inserted["audit_logs"][0]["metadata"]["context_budget_tokens"] == 120
    assert (
        db.inserted["audit_logs"][0]["metadata"]["context_pack_tokens_estimated"]
        <= 120
    )
    assert len(db.inserted["audit_logs"][0]["metadata"]["facts_considered"]) == 30
    assert db.inserted["audit_logs"][0]["metadata"]["retrieval_count"] == 30
    assert db.inserted["audit_logs"][0]["metadata"]["candidate_count"] == 30
    assert db.inserted["audit_logs"][0]["metadata"]["selected_count"] == len(
        result["facts_used"],
    )
    assert (
        db.inserted["audit_logs"][0]["metadata"]["ranking_strategy"]
        == "deterministic_v1"
    )
    assert db.inserted["audit_logs"][0]["metadata"]["facts_used"] == result["facts_used"]
    assert "context_pack_hash" in db.inserted["audit_logs"][0]["metadata"]


def test_query_limits_candidates_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_MAX_CANDIDATE_FACTS", "2")
    monkeypatch.setenv("QUERY_MAX_CANDIDATE_RULES", "1")
    get_settings.cache_clear()
    db = QueryDB()
    for index in range(5):
        db.published_sources.append(_published_source(f"source_published_{index}"))
        db.published_facts.append(
            _published_price_fact(
                id=f"fact_published_price_{index}",
                source_id=f"source_published_{index}",
                content={"service": f"servico {index}", "price": f"R$ {50 + index}"},
                normalized_content={"service": f"servico {index}", "price": 50 + index},
            )
        )

    result = _answer_query(db, "Precos servicos")

    metadata = db.inserted["audit_logs"][0]["metadata"]
    assert len(metadata["facts_considered"]) == 2
    assert metadata["candidate_count"] == 2
    assert len(result["facts_used"]) <= 2
    assert ("published_facts", "limit", "count", 2) in db.filters


def test_query_single_over_budget_fact_returns_partial_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUERY_CONTEXT_BUDGET_TOKENS", "120")
    get_settings.cache_clear()
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.published_facts.append(
        _published_price_fact(
            content={
                "service": "corte",
                "price": "R$ 50",
                "description": "descricao longa " * 500,
            },
            normalized_content={
                "service": "corte",
                "price": 50,
                "currency": "BRL",
                "description": "descricao longa " * 500,
            },
        )
    )

    result = _query_service().answer_query(
        db,
        workspace_id=WORKSPACE_ID,
        question="Qual o preco do corte?",
        actor_user_id=USER_ID,
        max_output_tokens=None,
        include_evidence=True,
    )

    assert result["answer_state"] == "partial_answer"
    assert result["facts_used"] == []
    assert result["usage"]["context_pack_tokens_estimated"] == 0
    assert result["missing_data"] == ["context_budget"]


def test_query_unrelated_published_fact_returns_not_found() -> None:
    db = QueryDB()
    db.published_facts.append(
        _published_price_fact(
            id="fact_hours_1",
            fact_type="business_hours",
            content={"weekday": "segunda", "open_time": "09:00"},
            normalized_content={"weekday": "segunda", "open_time": "09:00"},
        )
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["facts_used"] == []
    assert result["sources_used"] == []
    assert "09:00" not in result["answer"]


def test_post_query_rejects_unknown_membership_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    db = QueryDB()
    db.rows["workspace_members"] = [
        {
            "workspace_id": WORKSPACE_ID,
            "user_id": USER_ID,
            "role": "contractor",
        }
    ]
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": USER_ID,
        "email": "u@test.com",
    }
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db

    response = TestClient(app).post(
        f"/workspaces/{WORKSPACE_ID}/query",
        json={"question": "Qual o preco do corte?"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "invalid_workspace_role"
    assert db.inserted["query_audits"] == []


def test_query_unrelated_pending_data_returns_not_found() -> None:
    db = QueryDB()
    db.extracted_facts.append(
        _pending_price_fact(
            fact_type="business_hours",
            content={"weekday": "segunda", "open_time": "09:00"},
            normalized_content={"weekday": "segunda", "open_time": "09:00"},
        )
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["missing_data"] == ["published_data"]


def test_query_unrelated_open_contradiction_does_not_block_answer() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_published_1"),
            _published_source("source_hours_1"),
        ]
    )
    db.published_facts.append(_published_price_fact())
    db.published_facts.append(
        _published_price_fact(
            id="fact_hours_1",
            fact_type="business_hours",
            source_id="source_hours_1",
            chunk_id="chunk_hours_1",
            content={"weekday": "segunda", "open_time": "09:00"},
            normalized_content={"weekday": "segunda", "open_time": "09:00"},
        )
    )
    db.contradictions.append(
        _open_contradiction(
            fact_ids=["fact_hours_1", "fact_hours_2"],
            source_ids=["source_hours_1", "source_hours_2"],
        )
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "valid_answer"
    assert result["facts_used"] == ["fact_published_price_1"]
    assert result["warnings"] == []


def test_query_specific_service_does_not_return_other_service_price() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_barba_1"),
            _published_source("source_published_1"),
        ]
    )
    db.published_facts.append(
        _published_price_fact(
            id="fact_barba_price_1",
            source_id="source_barba_1",
            chunk_id="chunk_barba_1",
            content={"service": "barba", "price": "R$ 30"},
            normalized_content={"service": "barba", "price": 30, "currency": "BRL"},
        )
    )
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "valid_answer"
    assert result["facts_used"] == ["fact_published_price_1"]
    assert "R$ 30" not in result["answer"]


def test_query_ranks_exact_service_match_before_generic_high_confidence_fact() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_generic_1"),
            _published_source("source_published_1"),
        ]
    )
    db.published_facts.append(
        _published_price_fact(
            id="fact_generic_price_1",
            source_id="source_generic_1",
            chunk_id="chunk_generic_1",
            evidence_span_id=None,
            content={"category": "precos servicos", "price": "consulte tabela"},
            normalized_content={"category": "precos servicos", "price": "varios"},
            confidence=0.99,
            published_at="2026-05-14T10:00:00Z",
        )
    )
    db.published_facts.append(
        _published_price_fact(
            confidence=0.80,
            published_at="2026-05-13T10:00:00Z",
        )
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "valid_answer"
    assert result["facts_used"] == ["fact_published_price_1", "fact_generic_price_1"]
    assert result["answer"].index("corte") < result["answer"].index("precos servicos")
    assert db.inserted["audit_logs"][0]["metadata"]["facts_considered"] == [
        "fact_published_price_1",
        "fact_generic_price_1",
    ]


def test_query_ranks_by_confidence_and_recency_after_equal_relevance() -> None:
    db = QueryDB()
    db.published_sources.extend(
        [
            _published_source("source_low_1"),
            _published_source("source_high_1"),
            _published_source("source_recent_1"),
        ]
    )
    db.published_facts.extend(
        [
            _published_price_fact(
                id="fact_low_confidence_1",
                source_id="source_low_1",
                chunk_id="chunk_low_1",
                evidence_span_id=None,
                content={"service": "corte", "price": "R$ 55"},
                normalized_content={"service": "corte", "price": 55},
                confidence=0.7,
                published_at="2026-05-13T10:00:00Z",
            ),
            _published_price_fact(
                id="fact_high_confidence_1",
                source_id="source_high_1",
                chunk_id="chunk_high_1",
                evidence_span_id=None,
                content={"service": "corte", "price": "R$ 50"},
                normalized_content={"service": "corte", "price": 50},
                confidence=0.95,
                published_at="2026-05-12T10:00:00Z",
            ),
            _published_price_fact(
                id="fact_recent_tiebreak_1",
                source_id="source_recent_1",
                chunk_id="chunk_recent_1",
                evidence_span_id=None,
                content={"service": "corte", "price": "R$ 60"},
                normalized_content={"service": "corte", "price": 60},
                confidence=0.95,
                published_at="2026-05-14T10:00:00Z",
            ),
        ]
    )

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["facts_used"] == [
        "fact_recent_tiebreak_1",
        "fact_high_confidence_1",
        "fact_low_confidence_1",
    ]


def test_query_ignores_non_published_rows_in_published_tables() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source())
    db.published_facts.append(_published_price_fact(status="approved"))

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["facts_used"] == []


def test_query_generates_audit_id_when_insert_returns_no_representation() -> None:
    db = QueryDB()
    db.return_insert_data = False
    db.published_sources.append(_published_source())
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["audit_id"]
    assert db.inserted["query_audits"][0]["id"] == result["audit_id"]
    assert db.inserted["audit_logs"][0]["resource_id"] == result["audit_id"]


def test_query_excludes_fact_when_source_is_not_published() -> None:
    db = QueryDB()
    db.published_sources.append(_published_source("source_other"))
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["facts_used"] == []


def test_query_excludes_fact_without_published_source_record() -> None:
    db = QueryDB()
    db.published_facts.append(_published_price_fact())

    result = _answer_query(db, "Qual o preco do corte?")

    assert result["answer_state"] == "not_found"
    assert result["facts_used"] == []
