from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from supabase import Client

_STOPWORDS = frozenset(
    {
        "a",
        "as",
        "com",
        "da",
        "de",
        "do",
        "e",
        "em",
        "o",
        "os",
        "qual",
        "quais",
        "que",
        "tem",
        "para",
        "por",
        "um",
        "uma",
    }
)
_INTENT_TERMS = {
    "service_price": {
        "preco",
        "precos",
        "valor",
        "valores",
        "custa",
        "custam",
        "servico",
        "servicos",
    },
    "business_hours": {"horario", "horarios", "abre", "fecha", "segunda", "sabado", "domingo"},
    "discount_rule": {"desconto", "pix", "promocao"},
    "payment_method": {"pagamento", "pix", "cartao", "dinheiro"},
    "contact_info": {"telefone", "contato", "email", "endereco"},
    "faq_item": {"como", "duvida", "pergunta"},
}
_ALL_INTENT_TERMS = frozenset().union(*_INTENT_TERMS.values())
RANKING_STRATEGY = "deterministic_v1"
BLOCKING_CONTRADICTION_STATUSES = frozenset({"open", "needs_review"})
PENDING_FACT_RULE_STATUSES = frozenset({"extracted", "needs_review"})
OPEN_UNKNOWN_STATUSES = frozenset({"open"})


@dataclass(frozen=True)
class PublishedContext:
    sources: list[dict[str, Any]]
    facts: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    facts_considered: list[str]
    rules_considered: list[str]


def load_published_context(
    db: Client,
    *,
    workspace_id: str,
    question: str,
    max_candidate_facts: int,
    max_candidate_rules: int,
) -> PublishedContext:
    published_sources = only_published_rows(
        query_table(db, "published_sources", workspace_id=workspace_id),
    )
    published_facts = only_published_rows(
        filter_by_published_sources(
            query_table(
                db,
                "published_facts",
                workspace_id=workspace_id,
                row_limit=max_candidate_facts,
            ),
            published_sources,
        )
    )
    published_rules = only_published_rows(
        filter_by_published_sources(
            query_table(
                db,
                "published_rules",
                workspace_id=workspace_id,
                row_limit=max_candidate_rules,
            ),
            published_sources,
        )
    )
    relevant_facts = rank_rows(
        filter_relevant(published_facts, question),
        question,
    )[:max_candidate_facts]
    relevant_rules = rank_rows(
        filter_relevant(published_rules, question),
        question,
    )[:max_candidate_rules]
    return PublishedContext(
        sources=published_sources,
        facts=relevant_facts,
        rules=relevant_rules,
        facts_considered=[str(row["id"]) for row in relevant_facts if row.get("id")],
        rules_considered=[str(row["id"]) for row in relevant_rules if row.get("id")],
    )


def query_table(
    db: Client,
    table_name: str,
    *,
    workspace_id: str,
    row_limit: int | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.table(table_name)
        .select("*")
        .eq("workspace_id", workspace_id)
    )
    if row_limit is not None:
        query = query.limit(row_limit)
    return as_list(
        query.execute().data
    )


def query_evidence_spans(
    db: Client,
    *,
    workspace_id: str,
    evidence_span_ids: list[str],
) -> list[dict[str, Any]]:
    if not evidence_span_ids:
        return []
    return as_list(
        db.table("evidence_spans")
        .select("*")
        .eq("workspace_id", workspace_id)
        .in_("id", evidence_span_ids)
        .execute()
        .data
    )


def filter_by_published_sources(
    rows: list[dict[str, Any]],
    published_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    allowed_source_ids = {
        str(row["id"])
        for row in published_sources
        if row.get("id") is not None
    }
    return [
        row
        for row in rows
        if row.get("source_id") is not None and str(row["source_id"]) in allowed_source_ids
    ]


def index_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): row
        for row in rows
        if row.get("id") is not None
    }


def open_relevant_contradictions(
    db: Client,
    *,
    workspace_id: str,
    published_facts: list[dict[str, Any]],
    published_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not published_facts and not published_rules:
        return []
    return relevant_contradictions(
        open_contradictions(db, workspace_id=workspace_id),
        fact_ids={str(row["id"]) for row in published_facts if row.get("id")},
        rule_ids={str(row["id"]) for row in published_rules if row.get("id")},
    )


def open_contradictions(db: Client, *, workspace_id: str) -> list[dict[str, Any]]:
    return as_list(
        db.table("contradictions")
        .select("*")
        .eq("workspace_id", workspace_id)
        .in_("status", sorted(BLOCKING_CONTRADICTION_STATUSES))
        .execute()
        .data
    )


def has_pending_data(db: Client, *, workspace_id: str, question: str) -> bool:
    pending_facts = query_table(db, "extracted_facts", workspace_id=workspace_id)
    pending_rules = query_table(db, "business_rules", workspace_id=workspace_id)
    relevant_facts_and_rules = filter_relevant(pending_facts + pending_rules, question)
    if any(row.get("status") in PENDING_FACT_RULE_STATUSES for row in relevant_facts_and_rules):
        return True
    pending_unknowns = query_table(db, "unknown_facts_queue", workspace_id=workspace_id)
    relevant_unknowns = filter_relevant(pending_unknowns, question)
    return any(row.get("status") in OPEN_UNKNOWN_STATUSES for row in relevant_unknowns)


def source_ids_from_contradictions(contradictions: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for contradiction in contradictions:
        for source_id in contradiction.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id not in seen:
                seen.add(source_id)
                ordered.append(source_id)
    return ordered


def relevant_contradictions(
    contradictions: list[dict[str, Any]],
    *,
    fact_ids: set[str],
    rule_ids: set[str],
) -> list[dict[str, Any]]:
    relevant: list[dict[str, Any]] = []
    for contradiction in contradictions:
        contradiction_fact_ids = {str(value) for value in contradiction.get("fact_ids", []) or []}
        contradiction_rule_ids = {str(value) for value in contradiction.get("rule_ids", []) or []}
        if contradiction_fact_ids & fact_ids or contradiction_rule_ids & rule_ids:
            relevant.append(contradiction)
    return relevant


def filter_relevant(rows: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    question_terms = tokens(question)
    return [row for row in rows if is_relevant(row, question_terms)]


def rank_rows(rows: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    question_terms = tokens(question)
    return sorted(rows, key=lambda row: ranking_key(row, question_terms))


def only_published_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("status") == "published"]


def as_list(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def tokens(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    }


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def is_relevant(row: dict[str, Any], question_terms: set[str]) -> bool:
    if not question_terms:
        return False
    row_terms = tokens(row_text(row))
    entity_terms = get_entity_terms(question_terms)
    if has_entity_mismatch(row, entity_terms):
        return False
    if entity_terms and entity_terms & row_terms:
        return True
    if intent_matched(row, question_terms):
        return True
    return bool(question_terms & row_terms)


def row_text(row: dict[str, Any]) -> str:
    payload = {
        "fact_type": row.get("fact_type"),
        "rule_type": row.get("rule_type"),
        "suggested_fact_type": row.get("suggested_fact_type"),
        "raw_text": row.get("raw_text"),
        "content": row.get("content"),
        "normalized_content": row.get("normalized_content"),
        "suggested_schema": row.get("suggested_schema"),
        "condition": row.get("condition"),
        "action": row.get("action"),
    }
    return json.dumps(payload, sort_keys=True, default=str).lower()


def ranking_key(row: dict[str, Any], question_terms: set[str]) -> tuple[Any, ...]:
    row_terms = tokens(row_text(row))
    entity_terms = get_entity_terms(question_terms)
    exact_entity_matches = len(entity_terms & explicit_entity_values(row))
    lexical_matches = len(question_terms & row_terms)
    return (
        -exact_entity_matches,
        -int(intent_matched(row, question_terms)),
        -lexical_matches,
        -confidence_value(row),
        -timestamp_value(row),
        str(row.get("id", "")),
    )


def row_kind(row: dict[str, Any]) -> str | None:
    value = row.get("fact_type") or row.get("rule_type")
    return value if isinstance(value, str) else None


def get_entity_terms(question_terms: set[str]) -> set[str]:
    return question_terms - _ALL_INTENT_TERMS


def intent_matched(row: dict[str, Any], question_terms: set[str]) -> bool:
    kind = row_kind(row)
    return bool(kind and question_terms & _INTENT_TERMS.get(kind, set()))


def explicit_entity_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for field in ("content", "normalized_content", "condition", "action"):
        payload = row.get(field)
        if not isinstance(payload, dict):
            continue
        for key in ("service", "service_name", "name", "entity", "topic"):
            value = payload.get(key)
            if isinstance(value, str):
                values.update(tokens(value))
    return values


def has_entity_mismatch(row: dict[str, Any], entity_terms: set[str]) -> bool:
    explicit_values = explicit_entity_values(row)
    specific_values = explicit_values - _ALL_INTENT_TERMS
    return bool(specific_values and entity_terms and not specific_values & entity_terms)


def timestamp_value(row: dict[str, Any]) -> float:
    for field in ("published_at", "updated_at", "created_at"):
        value = row.get(field)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return 0.0


def confidence_value(row: dict[str, Any]) -> float:
    value = row.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0
