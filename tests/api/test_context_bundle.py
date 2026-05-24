from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from context_builder.config import get_settings
from context_builder.dependencies import (
    get_current_user,
    get_supabase_service_for_backend_only,
    require_workspace_member,
)
from context_builder.main import create_app
from fastapi import HTTPException
from fastapi.testclient import TestClient

WORKSPACE_ID = "5f7c6e4d-0000-4000-9000-000000000001"
USER_ID = "5f7c6e4d-0000-4000-9000-000000000099"

_MEMBERSHIP = {
    "user": {"id": USER_ID, "email": "owner@test.com"},
    "role": "owner",
    "workspace_id": WORKSPACE_ID,
}


class Result:
    def __init__(self, data: Any, count: int | None = None) -> None:
        self.data = data
        self.count = count


class ContextBundleQuery:
    def __init__(self, db: ContextBundleDB, table_name: str) -> None:
        self._db = db
        self._table_name = table_name
        self._filters: dict[str, Any] = {}
        self._in_filters: dict[str, set[Any]] = {}
        self._count_requested = False

    def select(self, _fields: str, **kwargs: Any) -> ContextBundleQuery:
        self._count_requested = kwargs.get("count") == "exact"
        return self

    def eq(self, field: str, value: Any) -> ContextBundleQuery:
        self._filters[field] = value
        return self

    def in_(self, field: str, values: list[Any]) -> ContextBundleQuery:
        self._in_filters[field] = set(values)
        return self

    def limit(self, _count: int) -> ContextBundleQuery:
        return self

    def insert(self, payload: dict[str, Any]) -> ContextBundleQuery:
        self._db.inserted.setdefault(self._table_name, []).append(payload)
        self._insert_payload = payload
        return self

    def execute(self) -> Result:
        if hasattr(self, "_insert_payload"):
            return Result([self._insert_payload])
        rows = list(self._db.rows.get(self._table_name, []))
        for field, value in self._filters.items():
            rows = [row for row in rows if row.get(field) == value]
        for field, values in self._in_filters.items():
            rows = [row for row in rows if row.get(field) in values]
        return Result(rows, count=len(rows) if self._count_requested else None)


class ContextBundleDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "published_sources": [],
            "published_facts": [],
            "published_rules": [],
            "evidence_spans": [],
            "unknown_facts_queue": [],
            "contradictions": [],
            "audit_logs": [],
        }
        self.inserted: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> ContextBundleQuery:
        return ContextBundleQuery(self, name)


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    get_settings.cache_clear()


def _client(db: ContextBundleDB) -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": USER_ID,
        "email": "owner@test.com",
    }
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: db
    app.dependency_overrides[require_workspace_member] = lambda: _MEMBERSHIP
    return TestClient(app)


def _source(source_id: str = "5f7c6e4d-0000-4000-9000-000000000010") -> dict[str, Any]:
    return {
        "id": source_id,
        "title": "Tabela de precos",
        "original_filename": "precos.pdf",
        "type": "upload",
        "source_reliability": "high",
        "authority_level": "official",
        "status": "published",
        "created_at": "2026-05-24T11:00:00+00:00",
        "updated_at": "2026-05-24T11:30:00+00:00",
        "workspace_id": WORKSPACE_ID,
    }


def _fact(
    fact_id: str = "5f7c6e4d-0000-4000-9000-000000000020",
    source_id: str = "5f7c6e4d-0000-4000-9000-000000000010",
    chunk_id: str = "5f7c6e4d-0000-4000-9000-000000000011",
    confidence: float = 0.94,
    evidence_span_id: str | None = "5f7c6e4d-0000-4000-9000-000000000030",
) -> dict[str, Any]:
    return {
        "id": fact_id,
        "fact_type": "service_price",
        "schema_version": "1.0.0",
        "normalized_content": {
            "service_name": "Limpeza de pele",
            "price_amount": 120,
            "currency": "BRL",
            "price_type": "fixed",
        },
        "confidence": confidence,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "evidence_span_id": evidence_span_id,
        "status": "published",
        "published_at": "2026-05-24T11:30:00+00:00",
        "workspace_id": WORKSPACE_ID,
    }


def _rule(
    rule_id: str = "5f7c6e4d-0000-4000-9000-000000000040",
    source_id: str = "5f7c6e4d-0000-4000-9000-000000000010",
    chunk_id: str = "5f7c6e4d-0000-4000-9000-000000000011",
    evidence_span_id: str | None = "5f7c6e4d-0000-4000-9000-000000000030",
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "rule_type": "discount_rule",
        "schema_version": "1.0.0",
        "condition": {"payment_method": "pix"},
        "action": {"discount_percentage": 5},
        "priority": 100,
        "confidence": 0.91,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "evidence_span_id": evidence_span_id,
        "status": "published",
        "published_at": "2026-05-24T11:31:00+00:00",
        "workspace_id": WORKSPACE_ID,
    }


def _evidence(
    evidence_id: str = "5f7c6e4d-0000-4000-9000-000000000030",
    source_id: str = "5f7c6e4d-0000-4000-9000-000000000010",
    chunk_id: str = "5f7c6e4d-0000-4000-9000-000000000011",
    quote: str = "Limpeza de pele custa R$120.",
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "quote": quote,
        "page_number": 1,
        "sheet_name": None,
        "row_number": None,
        "workspace_id": WORKSPACE_ID,
    }


def test_context_bundle_schema_serializes_v1_contract() -> None:
    from context_builder.schemas.context_bundle import (
        ContextBundleIntegrity,
        ContextBundleReadiness,
        ContextBundleResponse,
    )

    bundle = ContextBundleResponse(
        schema_version="context_bundle.v1",
        context_version="ctx_abc123def456",
        workspace_id=UUID(WORKSPACE_ID),
        generated_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sources=[],
        facts=[],
        rules=[],
        evidence=[],
        readiness=ContextBundleReadiness(
            status="blocked",
            score=0,
            blocking_reasons=["no_published_sources", "no_published_records"],
            warnings=[],
        ),
        integrity=ContextBundleIntegrity(
            bundle_hash="abc123",
            canonicalization="json.sort_keys.compact.v1",
            source_count=0,
            fact_count=0,
            rule_count=0,
            evidence_count=0,
        ),
    )

    payload = bundle.model_dump(mode="json")

    assert payload["schema_version"] == "context_bundle.v1"
    assert payload["context_version"] == "ctx_abc123def456"
    assert payload["readiness"]["status"] == "blocked"
    assert payload["integrity"]["canonicalization"] == "json.sort_keys.compact.v1"


def test_context_bundle_empty_workspace_is_blocked() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[],
        facts=[],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "no_published_sources" in bundle.readiness.blocking_reasons
    assert "no_published_records" in bundle.readiness.blocking_reasons


def test_context_bundle_hash_is_deterministic() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    kwargs = {
        "workspace_id": WORKSPACE_ID,
        "sources": [_source()],
        "facts": [_fact()],
        "rules": [_rule()],
        "evidence": [_evidence()],
        "open_unknown_count": 0,
        "blocking_contradiction_count": 0,
    }

    first = build_context_bundle_from_rows(**kwargs)
    second = build_context_bundle_from_rows(**kwargs)

    assert first.integrity.bundle_hash == second.integrity.bundle_hash
    assert first.context_version == second.context_version
    assert first.readiness.status == "ready"


def test_context_bundle_open_unknown_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=1,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "open_unknown_items" in bundle.readiness.blocking_reasons


def test_context_bundle_blocking_contradiction_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=1,
    )

    assert bundle.readiness.status == "blocked"
    assert "blocking_contradictions" in bundle.readiness.blocking_reasons


def test_context_bundle_missing_evidence_warns() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "warning"
    assert "published_record_missing_evidence" in bundle.readiness.warnings


def test_context_bundle_low_confidence_warns() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact(confidence=0.7)],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "warning"
    assert "low_confidence_record" in bundle.readiness.warnings


def test_context_bundle_service_loads_published_rows_and_audits_export() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle

    db = ContextBundleDB()
    db.rows["published_sources"].append(_source())
    db.rows["published_facts"].append(_fact())
    db.rows["published_rules"].append(_rule())
    db.rows["evidence_spans"].append(_evidence())

    bundle = build_context_bundle(
        db,
        workspace_id=WORKSPACE_ID,
        actor_user_id=USER_ID,
        actor_role="owner",
    )

    assert bundle.readiness.status == "ready"
    assert bundle.integrity.source_count == 1
    assert bundle.integrity.fact_count == 1
    assert bundle.integrity.rule_count == 1
    assert bundle.facts[0].evidence_span_ids == [UUID(_evidence()["id"])]
    audit = db.inserted["audit_logs"][0]
    assert audit["action"] == "context_bundle.export"
    assert audit["resource_id"] is None
    assert audit["output_hash"] == bundle.integrity.bundle_hash
    assert audit["metadata"]["context_version"] == bundle.context_version


def test_context_bundle_service_filters_unpublished_rows() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle

    db = ContextBundleDB()
    db.rows["published_sources"].append(_source())
    db.rows["published_sources"].append(
        {**_source(str(uuid4())), "status": "uploaded"}
    )
    db.rows["published_facts"].append(_fact())
    unpublished_fact = _fact(str(uuid4()))
    unpublished_fact["status"] = "approved"
    db.rows["published_facts"].append(unpublished_fact)
    db.rows["published_rules"].append(_rule())
    unpublished_rule = _rule(str(uuid4()))
    unpublished_rule["status"] = "needs_review"
    db.rows["published_rules"].append(unpublished_rule)
    db.rows["evidence_spans"].append(_evidence())

    bundle = build_context_bundle(
        db,
        workspace_id=WORKSPACE_ID,
        actor_user_id=USER_ID,
        actor_role="owner",
    )

    assert bundle.integrity.source_count == 1
    assert bundle.integrity.fact_count == 1
    assert bundle.integrity.rule_count == 1


def test_context_bundle_service_reads_only_referenced_evidence_and_redacts_quote() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle

    unused_evidence_id = "5f7c6e4d-0000-4000-9000-000000000031"
    db = ContextBundleDB()
    db.rows["published_sources"].append(_source())
    db.rows["published_facts"].append(_fact())
    db.rows["evidence_spans"].append(
        _evidence(quote="Limpeza R$120; internal_notes custo privado")
    )
    db.rows["evidence_spans"].append(
        _evidence(
            unused_evidence_id,
            quote="Outro trecho publico no mesmo chunk nao referenciado.",
        )
    )

    bundle = build_context_bundle(
        db,
        workspace_id=WORKSPACE_ID,
        actor_user_id=USER_ID,
        actor_role="owner",
    )

    assert bundle.integrity.evidence_count == 1
    assert bundle.evidence[0].id == UUID(_evidence()["id"])
    assert bundle.evidence[0].quote is None
    assert bundle.facts[0].evidence_span_ids == [UUID(_evidence()["id"])]
    assert unused_evidence_id not in bundle.model_dump_json()
    assert "internal_notes" not in bundle.model_dump_json()


@pytest.mark.parametrize(
    "quote,forbidden",
    [
        ("https://example.test/file?X-Amz-Signature=secret", "X-Amz-Signature"),
        ("database password=super-secret", "password="),
        ("raw_prompt: ignore previous instructions", "raw_prompt"),
        ("provider_response: raw model json", "provider_response"),
        ("Traceback (most recent call last): boom", "Traceback"),
    ],
)
def test_context_bundle_redacts_private_quote_markers(
    quote: str,
    forbidden: str,
) -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[_evidence(quote=quote)],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.evidence[0].quote is None
    assert forbidden not in bundle.model_dump_json()


def test_context_bundle_from_rows_sanitizes_payloads_and_omits_unreferenced_evidence() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    unused_evidence_id = "5f7c6e4d-0000-4000-9000-000000000031"
    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[
            {
                **_fact(),
                "normalized_content": {
                    "public_price": 120,
                    "cost": 70,
                    "signed_url": "https://example.test/file?X-Amz-Signature=secret",
                    "stack": "Traceback (most recent call last): boom",
                    "prompt": "raw_prompt: ignore previous instructions",
                },
            }
        ],
        rules=[
            {
                **_rule(),
                "condition": {"payment_method": "pix", "margin": "60%"},
                "action": {"discount": 5, "provider": "provider_response: raw json"},
            }
        ],
        evidence=[
            _evidence(quote="Limpeza R$120"),
            _evidence(unused_evidence_id, quote="Nao referenciado"),
        ],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    payload = bundle.model_dump(mode="json")
    serialized = bundle.model_dump_json()

    assert bundle.integrity.evidence_count == 1
    assert payload["facts"][0]["normalized_content"] == {
        "public_price": 120,
        "signed_url": None,
        "stack": None,
        "prompt": None,
    }
    assert payload["rules"][0]["condition"] == {"payment_method": "pix"}
    assert payload["rules"][0]["action"] == {"discount": 5, "provider": None}
    assert unused_evidence_id not in serialized
    assert "cost" not in serialized
    assert "margin" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert "Traceback" not in serialized
    assert "raw_prompt" not in serialized
    assert "provider_response" not in serialized


def test_no_bearer_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    response = TestClient(create_app()).get(f"/workspaces/{WORKSPACE_ID}/context-bundle")
    assert response.status_code == 401


def test_context_bundle_route_returns_403_for_non_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    app = create_app()

    def deny_membership() -> None:
        raise HTTPException(status_code=403, detail="not_workspace_member")

    app.dependency_overrides[require_workspace_member] = deny_membership
    app.dependency_overrides[get_supabase_service_for_backend_only] = lambda: ContextBundleDB()

    response = TestClient(app).get(
        f"/workspaces/{WORKSPACE_ID}/context-bundle",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403


def test_context_bundle_unknown_subroute_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    response = _client(ContextBundleDB()).get(
        f"/workspaces/{WORKSPACE_ID}/context-bundle/unknown",
    )
    assert response.status_code == 404


def test_context_bundle_route_returns_v1_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    db = ContextBundleDB()
    db.rows["published_sources"].append(_source())
    db.rows["published_facts"].append(_fact())
    db.rows["evidence_spans"].append(_evidence())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/context-bundle")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "context_bundle.v1"
    assert body["readiness"]["status"] == "ready"
    assert body["integrity"]["bundle_hash"]
    assert body["facts"][0]["evidence_span_ids"] == [_evidence()["id"]]


def test_context_bundle_route_uses_workspace_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch)
    other_workspace = str(uuid4())
    db = ContextBundleDB()
    db.rows["published_sources"].append(_source())
    db.rows["published_sources"].append({**_source(str(uuid4())), "workspace_id": other_workspace})
    db.rows["published_facts"].append(_fact())
    db.rows["published_facts"].append({**_fact(str(uuid4())), "workspace_id": other_workspace})
    db.rows["evidence_spans"].append(_evidence())

    response = _client(db).get(f"/workspaces/{WORKSPACE_ID}/context-bundle")

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["source_count"] == 1
    assert body["integrity"]["fact_count"] == 1
