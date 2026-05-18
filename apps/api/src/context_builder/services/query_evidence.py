from __future__ import annotations

from collections.abc import Callable
from typing import Any

from context_builder.services.query_redaction import redact_sensitive_quote

EvidenceSpanLoader = Callable[[list[str]], list[dict[str, Any]]]
MAX_EVIDENCE_QUOTE_CHARS = 500


def build_evidence_for_outcome(
    *,
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    user_role: str,
    include_evidence: bool,
    evidence_span_loader: EvidenceSpanLoader,
) -> list[dict[str, Any]]:
    if not include_evidence or not (facts or rules):
        return []
    evidence_span_ids: list[str] = []
    for row in facts + rules:
        evidence_span_id = row.get("evidence_span_id")
        if evidence_span_id is not None and str(evidence_span_id) not in evidence_span_ids:
            evidence_span_ids.append(str(evidence_span_id))
    evidence_spans = evidence_span_loader(evidence_span_ids) if evidence_span_ids else []
    return build_evidence(
        facts,
        rules,
        sources_by_id=sources_by_id,
        evidence_spans_by_id=index_by_id(evidence_spans),
        user_role=user_role,
    )


def index_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): row
        for row in rows
        if row.get("id") is not None
    }


def source_name(source: dict[str, Any] | None) -> str | None:
    if not source:
        return None
    for field in ("original_filename", "filename", "name", "title"):
        value = source.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def build_evidence(
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    *,
    sources_by_id: dict[str, dict[str, Any]],
    evidence_spans_by_id: dict[str, dict[str, Any]],
    user_role: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for fact in facts:
        evidence_span_id = fact.get("evidence_span_id")
        span = (
            evidence_spans_by_id.get(str(evidence_span_id))
            if evidence_span_id is not None
            else None
        )
        source = sources_by_id.get(str(fact["source_id"])) if fact.get("source_id") else None
        evidence.append(
            {
                "source_id": fact.get("source_id"),
                "source_name": source_name(source),
                "evidence_span_id": evidence_span_id,
                "quote": safe_quote(span.get("quote") if span else None, user_role=user_role),
                "page_number": span.get("page_number") if span else None,
                "sheet_name": span.get("sheet_name") if span else None,
                "row_number": span.get("row_number") if span else None,
                "chunk_id": (span.get("chunk_id") if span else None) or fact.get("chunk_id"),
                "fact_id": fact.get("id"),
                "rule_id": None,
            }
        )
    for rule in rules:
        evidence_span_id = rule.get("evidence_span_id")
        span = (
            evidence_spans_by_id.get(str(evidence_span_id))
            if evidence_span_id is not None
            else None
        )
        source = sources_by_id.get(str(rule["source_id"])) if rule.get("source_id") else None
        evidence.append(
            {
                "source_id": rule.get("source_id"),
                "source_name": source_name(source),
                "evidence_span_id": evidence_span_id,
                "quote": safe_quote(span.get("quote") if span else None, user_role=user_role),
                "page_number": span.get("page_number") if span else None,
                "sheet_name": span.get("sheet_name") if span else None,
                "row_number": span.get("row_number") if span else None,
                "chunk_id": (span.get("chunk_id") if span else None) or rule.get("chunk_id"),
                "fact_id": None,
                "rule_id": rule.get("id"),
            }
        )
    return evidence


def safe_quote(value: Any, *, user_role: str) -> str | None:
    quote = redact_sensitive_quote(value, user_role=user_role)
    if quote is None or len(quote) <= MAX_EVIDENCE_QUOTE_CHARS:
        return quote
    return quote[: MAX_EVIDENCE_QUOTE_CHARS - 3].rstrip() + "..."
