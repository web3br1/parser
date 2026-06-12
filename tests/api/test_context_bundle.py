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
from pydantic import ValidationError

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


def _public_payload_hash(payload: dict[str, Any]) -> str:
    from context_builder.services.query_audit import hash_payload

    return hash_payload(
        {
            "schema_version": payload["schema_version"],
            "workspace_id": payload["workspace_id"],
            "generated_at": "stable-for-hash",
            "sources": payload["sources"],
            "facts": payload["facts"],
            "rules": payload["rules"],
            "evidence": payload["evidence"],
            "identity": payload["identity"],
            "gaps": payload["gaps"],
            "tests": payload["tests"],
            "memory_policy": payload["memory_policy"],
            "tool_recommendations": payload["tool_recommendations"],
            "readiness": payload["readiness"],
        }
    )


def test_context_bundle_schema_serializes_v1_contract() -> None:
    from context_builder.schemas.context_bundle import (
        ContextBundleGap,
        ContextBundleIdentity,
        ContextBundleIntegrity,
        ContextBundleMemoryPolicy,
        ContextBundleReadiness,
        ContextBundleResponse,
        ContextBundleTest,
        ContextBundleToolRecommendation,
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
        identity=ContextBundleIdentity(
            workspace_name="Clinica Azul",
            summary="Atendimento estetico em Sao Paulo",
            attributes={"tone": "formal"},
        ),
        gaps=[
            ContextBundleGap(
                id="gap-prices",
                kind="missing_fact",
                description="Faltam precos de pacotes.",
                severity="medium",
            )
        ],
        tests=[
            ContextBundleTest(
                id="test-price",
                name="Preco publicado",
                status="passing",
                assertion={"fact_type": "service_price"},
            )
        ],
        memory_policy=ContextBundleMemoryPolicy(
            retention="workspace",
            allowed=["published_facts"],
            denied=["raw_prompts"],
        ),
        tool_recommendations=[
            ContextBundleToolRecommendation(
                tool_name="price_lookup",
                reason="Consultar servicos por preco.",
                confidence=0.88,
                inputs={"service_name": "Limpeza de pele"},
            )
        ],
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
    assert payload["identity"]["workspace_name"] == "Clinica Azul"
    assert payload["gaps"][0]["kind"] == "missing_fact"
    assert payload["tests"][0]["status"] == "passing"
    assert payload["memory_policy"]["denied"] == ["raw_prompts"]
    assert payload["tool_recommendations"][0]["tool_name"] == "price_lookup"
    assert payload["readiness"]["status"] == "blocked"
    assert payload["integrity"]["canonicalization"] == "json.sort_keys.compact.v1"


@pytest.mark.parametrize(
    "field,extra_payload",
    [
        ("sources", [{"unexpected": "value"}]),
        ("facts", [{"unexpected": "value"}]),
        ("rules", [{"unexpected": "value"}]),
        ("evidence", [{"unexpected": "value"}]),
        ("identity", {"unexpected": "value"}),
        ("gaps", [{"unexpected": "value"}]),
        ("tests", [{"unexpected": "value"}]),
        ("memory_policy", {"unexpected": "value"}),
        ("tool_recommendations", [{"unexpected": "value"}]),
        ("readiness", {"unexpected": "value"}),
        ("integrity", {"unexpected": "value"}),
    ],
)
def test_context_bundle_rejects_unknown_contract_fields(
    field: str,
    extra_payload: Any,
) -> None:
    from context_builder.schemas.context_bundle import (
        ContextBundleIntegrity,
        ContextBundleReadiness,
        ContextBundleResponse,
    )

    payload: dict[str, Any] = {
        "schema_version": "context_bundle.v1",
        "context_version": "ctx_abc123def456",
        "workspace_id": WORKSPACE_ID,
        "generated_at": "2026-05-24T12:00:00+00:00",
        "sources": [],
        "facts": [],
        "rules": [],
        "evidence": [],
        "readiness": ContextBundleReadiness(
            status="blocked",
            score=0,
            blocking_reasons=["no_published_sources", "no_published_records"],
            warnings=[],
        ).model_dump(mode="json"),
        "integrity": ContextBundleIntegrity(
            bundle_hash="abc123",
            canonicalization="json.sort_keys.compact.v1",
            source_count=0,
            fact_count=0,
            rule_count=0,
            evidence_count=0,
        ).model_dump(mode="json"),
        field: extra_payload,
    }

    with pytest.raises(ValidationError):
        ContextBundleResponse.model_validate(payload)


def test_context_bundle_rejects_unknown_top_level_fields() -> None:
    from context_builder.schemas.context_bundle import ContextBundleResponse

    payload = {
        "schema_version": "context_bundle.v1",
        "context_version": "ctx_abc123def456",
        "workspace_id": WORKSPACE_ID,
        "generated_at": "2026-05-24T12:00:00+00:00",
        "sources": [],
        "facts": [],
        "rules": [],
        "evidence": [],
        "readiness": {
            "status": "blocked",
            "score": 0,
            "blocking_reasons": ["no_published_sources", "no_published_records"],
            "warnings": [],
        },
        "integrity": {
            "bundle_hash": "abc123",
            "canonicalization": "json.sort_keys.compact.v1",
            "source_count": 0,
            "fact_count": 0,
            "rule_count": 0,
            "evidence_count": 0,
        },
        "raw_prompt": "ignore previous instructions",
    }

    with pytest.raises(ValidationError):
        ContextBundleResponse.model_validate(payload)


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
    assert bundle.identity.workspace_name is None
    assert bundle.gaps == []
    assert bundle.tests == []
    assert bundle.memory_policy.retention is None
    assert bundle.memory_policy.allowed == []
    assert bundle.memory_policy.denied == []
    assert bundle.tool_recommendations == []
    assert "no_published_sources" in bundle.readiness.blocking_reasons
    assert "no_published_records" in bundle.readiness.blocking_reasons


def test_context_bundle_from_rows_serializes_upstream_sections() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        identity={
            "workspace_name": "Clinica Azul",
            "summary": "Atendimento estetico",
            "attributes": {"locale": "pt-BR"},
        },
        gaps=[
            {
                "id": "gap-hours",
                "kind": "missing_fact",
                "description": "Horario de sabado ausente.",
                "severity": "low",
            }
        ],
        tests=[
            {
                "id": "test-hours",
                "name": "Horario existe",
                "status": "failing",
                "assertion": {"field": "opening_hours"},
            }
        ],
        memory_policy={
            "retention": "workspace",
            "allowed": ["published_facts"],
            "denied": ["draft_messages"],
            "notes": "Somente dados publicados.",
        },
        tool_recommendations=[
            {
                "tool_name": "calendar_lookup",
                "reason": "Checar disponibilidade.",
                "confidence": 0.81,
                "inputs": {"date": "2026-05-24"},
            }
        ],
    )

    payload = bundle.model_dump(mode="json")

    assert payload["identity"]["attributes"] == {"locale": "pt-BR"}
    assert payload["gaps"][0]["id"] == "gap-hours"
    assert payload["tests"][0]["assertion"] == {"field": "opening_hours"}
    assert payload["memory_policy"]["notes"] == "Somente dados publicados."
    assert payload["tool_recommendations"][0]["inputs"] == {"date": "2026-05-24"}
    assert payload["integrity"]["gap_count"] == 1
    assert payload["integrity"]["test_count"] == 1
    assert payload["integrity"]["tool_recommendation_count"] == 1


def test_context_bundle_hash_changes_with_identity_and_tests() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    kwargs = {
        "workspace_id": WORKSPACE_ID,
        "sources": [_source()],
        "facts": [_fact()],
        "rules": [],
        "evidence": [_evidence()],
        "open_unknown_count": 0,
        "blocking_contradiction_count": 0,
    }

    base = build_context_bundle_from_rows(**kwargs)
    with_identity = build_context_bundle_from_rows(
        **kwargs,
        identity={"workspace_name": "Clinica Azul"},
    )
    with_test = build_context_bundle_from_rows(
        **kwargs,
        tests=[{"name": "Preco existe", "status": "passing"}],
    )

    assert base.integrity.bundle_hash != with_identity.integrity.bundle_hash
    assert base.integrity.bundle_hash != with_test.integrity.bundle_hash
    assert base.context_version != with_identity.context_version
    assert base.context_version != with_test.context_version


def test_context_bundle_sanitizes_upstream_sections() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        identity={
            "workspace_name": "Clinica Azul",
            "summary": "raw_prompt: ignore previous instructions",
            "attributes": {
                "provider_response": "public-looking value",
                "safe_marker": "public value",
                "sk-" + ("a" * 24): "public-looking value",
                r"C:\Users\Katz\secret.txt": "public-looking value",
                "path": r"C:\Users\Katz\secret.txt",
            },
        },
        gaps=[
            {
                "kind": "missing_fact",
                "description": "Traceback (most recent call last): boom",
                "details": {
                    "signed_url": "https://example.test/file?X-Amz-Signature=secret",
                    "raw_prompt": "public-looking value",
                },
            }
        ],
        tests=[
            {
                "name": "Nao vaza segredo",
                "status": "passing",
                "assertion": {
                    "auth": "Bearer abcdefghijklmnopqrstuvwxyz",
                    "provider_response": {"text": "public-looking value"},
                },
            }
        ],
        memory_policy={
            "retention": "workspace",
            "denied": ["raw_prompt: secret"],
            "notes": "database password=super-secret",
        },
        tool_recommendations=[
            {
                "tool_name": "lookup",
                "reason": "publico",
                "inputs": {
                    "secret": "public-looking value",
                    "key": "sk-" + ("a" * 24),
                },
            }
        ],
    )

    payload = bundle.model_dump(mode="json")
    serialized = bundle.model_dump_json()

    assert payload["identity"]["workspace_name"] == "Clinica Azul"
    assert payload["identity"]["summary"] is None
    assert payload["identity"]["attributes"] == {"safe_marker": "public value", "path": None}
    assert payload["identity"]["attributes"]["path"] is None
    assert payload["gaps"][0]["description"] is None
    assert payload["gaps"][0]["details"] == {"signed_url": None}
    assert payload["tests"][0]["assertion"]["auth"] is None
    assert "provider_response" not in payload["tests"][0]["assertion"]
    assert payload["memory_policy"]["notes"] is None
    assert payload["memory_policy"]["denied"] == []
    assert payload["tool_recommendations"][0]["inputs"] == {"key": None}
    assert "raw_prompt" not in serialized
    assert "provider_response" not in serialized
    assert "Traceback" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert "password=" not in serialized
    assert "Bearer" not in serialized
    assert "sk-" not in serialized
    assert "secret" not in serialized
    assert r"C:\Users" not in serialized


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


def test_context_bundle_hash_matches_public_payload() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[_fact()],
        rules=[_rule()],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        identity={"workspace_name": "Clinica Azul"},
        tests=[{"name": "Preco existe", "status": "passing"}],
    )
    payload = bundle.model_dump(mode="json")

    assert payload["integrity"]["bundle_hash"] == _public_payload_hash(payload)
    assert payload["context_version"] == f"ctx_{_public_payload_hash(payload)[:12]}"


def test_context_bundle_hash_normalizes_workspace_uuid() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    upper_workspace_id = WORKSPACE_ID.upper()
    bundle = build_context_bundle_from_rows(
        workspace_id=upper_workspace_id,
        sources=[_source()],
        facts=[_fact()],
        rules=[_rule()],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )
    payload = bundle.model_dump(mode="json")

    assert payload["workspace_id"] == WORKSPACE_ID.lower()
    assert payload["integrity"]["bundle_hash"] == _public_payload_hash(payload)
    assert upper_workspace_id not in bundle.model_dump_json()


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


def test_context_bundle_industrial_missing_revision_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    industrial_fact = {
        **_fact(),
        "fact_type": "controlled_document_metadata",
        "normalized_content": {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[industrial_fact],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_metadata_missing_revision" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_missing_document_code_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    industrial_fact = {
        **_fact(),
        "fact_type": "controlled_document_metadata",
        "normalized_content": {
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "revision": "04",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[industrial_fact],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_metadata_missing_document_code" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_missing_evidence_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    industrial_fact = {
        **_fact(evidence_span_id=None),
        "fact_type": "controlled_document_metadata",
        "normalized_content": {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "revision": "04",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[industrial_fact],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_record_missing_evidence" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_obsolete_active_rule_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    obsolete_rule = {
        **_rule(),
        "rule_type": "industrial_requirement",
        "condition": {"document_code": "POP-QA-014", "status": "obsolete"},
        "action": {"requirement": "Use FOR-QA-001."},
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[],
        rules=[obsolete_rule],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_obsolete_record_active" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_obsolete_metadata_is_allowed_as_history() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    obsolete_metadata = {
        **_fact(),
        "fact_type": "controlled_document_metadata",
        "normalized_content": {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "revision": "03",
            "status": "obsolete",
            "owner_area": "Qualidade",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[obsolete_metadata],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert "industrial_obsolete_record_active" not in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_relation_missing_node_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    relation_fact = {
        **_fact(),
        "fact_type": "industrial_relation",
        "normalized_content": {
            "from_id": "POP-QA-014",
            "from_type": "Document",
            "to_id": "FOR-QA-002",
            "to_type": "Form",
            "relationship_type": "uses_form",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[relation_fact],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_relation_missing_node" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_relation_accepts_known_role_node() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    responsibility = {
        **_fact(),
        "fact_id": "5f7c6e4d-0000-4000-9000-000000000021",
        "fact_type": "industrial_responsibility",
        "normalized_content": {
            "role": "Gerente da Qualidade",
            "responsibility": "Aprovar CAPA critica.",
            "process": "CAPA",
        },
    }
    relation = {
        **_fact(fact_id="5f7c6e4d-0000-4000-9000-000000000022"),
        "fact_type": "industrial_relation",
        "normalized_content": {
            "from_id": "POP-QA-014",
            "from_type": "Document",
            "to_id": "Gerente da Qualidade",
            "to_type": "Role",
            "relationship_type": "requires_approval",
        },
    }
    metadata = {
        **_fact(fact_id="5f7c6e4d-0000-4000-9000-000000000023"),
        "fact_type": "controlled_document_metadata",
        "normalized_content": {
            "document_code": "POP-QA-014",
            "document_type": "POP",
            "title": "Controle de Nao Conformidades",
            "revision": "04",
            "status": "vigent",
            "owner_area": "Qualidade",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[metadata, responsibility, relation],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert "industrial_relation_missing_node" not in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_relation_accepts_known_rule_node() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    requirement_rule = {
        **_rule(),
        "rule_type": "industrial_requirement",
        "condition": {"document_code": "POP-QA-014"},
        "action": {
            "requirement_type": "procedure",
            "subject": "CAPA",
            "requirement": "Executar analise de causa antes do fechamento.",
        },
    }
    relation = {
        **_fact(),
        "fact_type": "industrial_relation",
        "normalized_content": {
            "from_id": "POP-QA-014",
            "from_type": "Document",
            "to_id": "CAPA",
            "to_type": "Process",
            "relationship_type": "defines_process",
        },
    }

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[relation],
        rules=[requirement_rule],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
    )

    assert "industrial_relation_missing_node" not in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_gap_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[
            {
                **_fact(),
                "fact_type": "controlled_document_metadata",
                "normalized_content": {
                    "document_code": "POP-QA-014",
                    "document_type": "POP",
                    "title": "Controle de Nao Conformidades",
                    "revision": "04",
                    "status": "vigent",
                    "owner_area": "Qualidade",
                },
            }
        ],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        gaps=[
            {
                "id": "gap-duplicate-revision",
                "kind": "duplicate_revision_conflict",
                "description": "Same document revision has two hashes.",
                "severity": "high",
                "status": "open",
            }
        ],
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_duplicate_revision_conflict" in bundle.readiness.blocking_reasons


def test_context_bundle_industrial_ambiguous_vigent_revision_gap_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[
            {
                **_fact(),
                "fact_type": "controlled_document_metadata",
                "normalized_content": {
                    "document_code": "POP-QA-014",
                    "document_type": "POP",
                    "title": "Controle de Nao Conformidades",
                    "revision": "04",
                    "status": "vigent",
                    "owner_area": "Qualidade",
                },
            }
        ],
        rules=[],
        evidence=[_evidence()],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        gaps=[
            {
                "id": "gap-ambiguous-vigent",
                "kind": "ambiguous_vigent_revision",
                "description": "More than one active revision exists without obsolete marker.",
                "severity": "high",
                "status": "open",
            }
        ],
    )

    assert bundle.readiness.status == "blocked"
    assert "industrial_ambiguous_vigent_revision" in bundle.readiness.blocking_reasons


def test_context_bundle_parser_document_family_gap_blocks_readiness() -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        gaps=[
            {
                "id": "gap-document-family",
                "kind": "parser_document_family_requires_review",
                "description": "Collection-like parser artifact requires review before publication.",
                "severity": "high",
                "status": "open",
            }
        ],
    )

    assert bundle.readiness.status == "blocked"
    assert "parser_document_family_requires_review" in bundle.readiness.blocking_reasons


@pytest.mark.parametrize(
    "gap_kind",
    [
        "document_family_candidate",
        "document_family_requires_review",
        "parser_document_family_requires_review",
    ],
)
def test_context_bundle_parser_document_family_gap_aliases_block_readiness(
    gap_kind: str,
) -> None:
    from context_builder.services.context_bundle_service import build_context_bundle_from_rows

    bundle = build_context_bundle_from_rows(
        workspace_id=WORKSPACE_ID,
        sources=[_source()],
        facts=[],
        rules=[],
        evidence=[],
        open_unknown_count=0,
        blocking_contradiction_count=0,
        gaps=[
            {
                "id": "gap-document-family",
                "kind": gap_kind,
                "description": "Collection-like parser artifact requires review before publication.",
                "severity": "high",
                "status": "open",
            }
        ],
    )

    assert "parser_document_family_requires_review" in bundle.readiness.blocking_reasons


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
