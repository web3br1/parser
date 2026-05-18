from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from supabase import Client


def new_query_audit_id() -> str:
    return str(uuid4())


def insert_row(db: Client, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = db.table(table_name).insert(payload).execute()
    rows = _as_list(result.data)
    return rows[0] if rows else dict(payload)


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def context_pack_hash(
    *,
    workspace_id: str,
    question: str,
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    contradictions: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "workspace_id": workspace_id,
        "question": question,
        "facts": facts,
        "rules": rules,
        "sources": sources,
        "evidence": evidence,
    }
    if contradictions is not None:
        payload["contradictions"] = contradictions
    return hash_payload(payload)


def persist_query_audit(
    db: Client,
    *,
    audit_id: str,
    workspace_id: str,
    actor_user_id: str,
    question: str,
    response: dict[str, Any],
    facts_considered: Sequence[str],
    rules_considered: Sequence[str],
    context_budget_tokens: int,
    context_pack_tokens_estimated: int,
    context_hash: str,
    token_input: int,
    token_output: int,
    ranking_strategy: str,
    request_metadata: dict[str, Any],
) -> str:
    audit_payload = {
        "id": audit_id,
        "workspace_id": workspace_id,
        "user_id": actor_user_id,
        "question": question,
        "answer": response["answer"],
        "answer_state": response["answer_state"],
        "facts_used": response["facts_used"],
        "rules_used": response["rules_used"],
        "sources_used": response["sources_used"],
        "used_unvalidated_data": False,
        "confidence": response["confidence"],
        "token_input": token_input,
        "token_output": token_output,
        "estimated_cost": 0.0,
    }
    query_audit = insert_row(db, "query_audits", audit_payload)
    audit_id = str(query_audit.get("id", audit_id))
    candidate_count = len(facts_considered) + len(rules_considered)
    selected_count = len(response["facts_used"]) + len(response["rules_used"])

    insert_row(
        db,
        "audit_logs",
        {
            "workspace_id": workspace_id,
            "actor_user_id": actor_user_id,
            "action": "query.answer",
            "resource_type": "query_audit",
            "resource_id": audit_id,
            "input_hash": hash_payload(
                {
                    "question": question,
                    "facts_considered": list(facts_considered),
                    "rules_considered": list(rules_considered),
                    "context_pack_hash": context_hash,
                    "request": request_metadata,
                }
            ),
            "output_hash": hash_payload(response),
            "metadata": {
                "answer_state": response["answer_state"],
                "retrieval_count": candidate_count,
                "candidate_count": candidate_count,
                "selected_count": selected_count,
                "ranking_strategy": ranking_strategy,
                "facts_considered": list(facts_considered),
                "rules_considered": list(rules_considered),
                "facts_used": response["facts_used"],
                "rules_used": response["rules_used"],
                "condensation_used": False,
                "context_budget_tokens": context_budget_tokens,
                "context_pack_tokens_estimated": context_pack_tokens_estimated,
                "context_pack_hash": context_hash,
                "request": request_metadata,
                "usage_is_estimated": True,
            },
        },
    )
    return audit_id


def _as_list(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []
