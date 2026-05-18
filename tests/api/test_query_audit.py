from __future__ import annotations

from typing import Any

from context_builder.services.query_audit import hash_payload, persist_query_audit


class AuditDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "query_audits": [],
            "audit_logs": [],
        }

    def table(self, name: str) -> AuditTable:
        return AuditTable(self, name)


class AuditResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class AuditTable:
    def __init__(self, db: AuditDB, table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self._insert_payload: dict[str, Any] | None = None

    def insert(self, payload: dict[str, Any]) -> AuditTable:
        self._insert_payload = payload
        return self

    def execute(self) -> AuditResult:
        assert self._insert_payload is not None
        stored = dict(self._insert_payload)
        self.db.rows[self.table_name].append(stored)
        return AuditResult(stored)


def test_persist_query_audit_uses_explicit_audit_id_without_mutating_response() -> None:
    db = AuditDB()
    response = {
        "audit_id": "audit_query_1",
        "answer_state": "valid_answer",
        "answer": "Resposta publica",
        "confidence": 0.9,
        "facts_used": ["fact_1"],
        "rules_used": [],
        "sources_used": ["source_1"],
        "used_unvalidated_data": False,
        "evidence": [],
        "missing_data": [],
        "warnings": [],
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }
    original_response = dict(response)

    audit_id = persist_query_audit(
        db,
        audit_id="audit_query_1",
        workspace_id="workspace_1",
        actor_user_id="user_1",
        question="Qual o preco?",
        response=response,
        facts_considered=["fact_1"],
        rules_considered=[],
        context_budget_tokens=6000,
        context_pack_tokens_estimated=100,
        context_hash="context_hash_1",
        token_input=10,
        token_output=4,
        ranking_strategy="deterministic_v1",
        request_metadata={
            "include_evidence": True,
            "max_output_tokens": 700,
            "user_role": "staff",
        },
    )

    assert audit_id == "audit_query_1"
    assert response == original_response
    assert db.rows["query_audits"][0]["id"] == "audit_query_1"
    assert db.rows["audit_logs"][0]["resource_id"] == "audit_query_1"
    assert db.rows["audit_logs"][0]["output_hash"] == hash_payload(original_response)
    assert db.rows["audit_logs"][0]["input_hash"] == hash_payload(
        {
            "question": "Qual o preco?",
            "facts_considered": ["fact_1"],
            "rules_considered": [],
            "context_pack_hash": "context_hash_1",
            "request": {
                "include_evidence": True,
                "max_output_tokens": 700,
                "user_role": "staff",
            },
        }
    )
    assert db.rows["audit_logs"][0]["metadata"]["request"] == {
        "include_evidence": True,
        "max_output_tokens": 700,
        "user_role": "staff",
    }
