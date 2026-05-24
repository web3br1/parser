from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from context_builder.schemas.context_bundle import (
    ContextBundleEvidence,
    ContextBundleFact,
    ContextBundleIntegrity,
    ContextBundleReadiness,
    ContextBundleResponse,
    ContextBundleRule,
    ContextBundleSource,
)
from context_builder.services.query_audit import hash_payload, insert_row
from context_builder.services.query_evidence import safe_quote
from context_builder.services.query_redaction import redact_sensitive
from context_builder.services.query_retrieval import only_published_rows
from supabase import Client

SCHEMA_VERSION: Literal["context_bundle.v1"] = "context_bundle.v1"
CANONICALIZATION = "json.sort_keys.compact.v1"
LOW_CONFIDENCE_THRESHOLD = 0.75
BUNDLE_QUOTE_ROLE = "viewer"
PRIVATE_QUOTE_PATTERNS = (
    re.compile(r"\b[A-Za-z]:\\(?:Users|Documents and Settings)\\", re.IGNORECASE),
    re.compile(r"(^|\s)/(?:Users|home|root)/", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:sb|sk|pk|rk|org|proj)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
)


def build_context_bundle(
    db: Client,
    *,
    workspace_id: str,
    actor_user_id: str,
    actor_role: str,
) -> ContextBundleResponse:
    sources = only_published_rows(_rows(
        db.table("published_sources")
        .select(
            "id,title,original_filename,type,source_reliability,authority_level,"
            "status,created_at,updated_at"
        )
        .eq("workspace_id", workspace_id)
        .execute()
        .data
    ))
    facts = only_published_rows(_rows(
        db.table("published_facts")
        .select(
            "id,fact_type,schema_version,normalized_content,confidence,"
            "source_id,chunk_id,evidence_span_id,status,published_at"
        )
        .eq("workspace_id", workspace_id)
        .execute()
        .data
    ))
    rules = only_published_rows(_rows(
        db.table("published_rules")
        .select(
            "id,rule_type,schema_version,condition,action,priority,confidence,"
            "source_id,chunk_id,evidence_span_id,status,published_at"
        )
        .eq("workspace_id", workspace_id)
        .execute()
        .data
    ))
    evidence = _load_evidence(db, workspace_id=workspace_id, facts=facts, rules=rules)
    open_unknown_count = _count(
        cast(Any, db.table("unknown_facts_queue"))
        .select("id", count="exact")
        .eq("workspace_id", workspace_id)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    blocking_contradiction_count = _count(
        cast(Any, db.table("contradictions"))
        .select("id", count="exact")
        .eq("workspace_id", workspace_id)
        .in_("status", ["open", "needs_review"])
        .limit(1)
        .execute()
    )
    bundle = build_context_bundle_from_rows(
        workspace_id=workspace_id,
        sources=sources,
        facts=facts,
        rules=rules,
        evidence=evidence,
        open_unknown_count=open_unknown_count,
        blocking_contradiction_count=blocking_contradiction_count,
    )
    _audit_export(db, bundle=bundle, actor_user_id=actor_user_id, actor_role=actor_role)
    return bundle


def build_context_bundle_from_rows(
    *,
    workspace_id: str,
    sources: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    open_unknown_count: int,
    blocking_contradiction_count: int,
) -> ContextBundleResponse:
    sorted_sources = _sort_rows(_published_or_statusless_rows(sources))
    sorted_facts = _sort_rows([
        _safe_record_row(row)
        for row in _published_or_statusless_rows(facts)
    ])
    sorted_rules = _sort_rows([
        _safe_record_row(row)
        for row in _published_or_statusless_rows(rules)
    ])
    sorted_evidence = _sort_rows(_referenced_evidence_rows(
        [_safe_evidence_row(row) for row in evidence],
        facts=sorted_facts,
        rules=sorted_rules,
    ))

    readiness = _readiness(
        sources=sorted_sources,
        facts=sorted_facts,
        rules=sorted_rules,
        evidence=sorted_evidence,
        open_unknown_count=open_unknown_count,
        blocking_contradiction_count=blocking_contradiction_count,
    )
    bundle_hash = _bundle_hash(
        workspace_id=workspace_id,
        sources=sorted_sources,
        facts=sorted_facts,
        rules=sorted_rules,
        evidence=sorted_evidence,
        readiness=readiness,
    )
    return ContextBundleResponse(
        schema_version=SCHEMA_VERSION,
        context_version=f"ctx_{bundle_hash[:12]}",
        workspace_id=UUID(workspace_id),
        generated_at=datetime.now(UTC),
        sources=[ContextBundleSource(**row) for row in sorted_sources],
        facts=[
            ContextBundleFact(**_with_evidence_ids(row, sorted_evidence))
            for row in sorted_facts
        ],
        rules=[
            ContextBundleRule(**_with_evidence_ids(row, sorted_evidence))
            for row in sorted_rules
        ],
        evidence=[ContextBundleEvidence(**row) for row in sorted_evidence],
        readiness=readiness,
        integrity=ContextBundleIntegrity(
            bundle_hash=bundle_hash,
            canonicalization=CANONICALIZATION,
            source_count=len(sorted_sources),
            fact_count=len(sorted_facts),
            rule_count=len(sorted_rules),
            evidence_count=len(sorted_evidence),
        ),
    )


def _bundle_hash(
    *,
    workspace_id: str,
    sources: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    readiness: ContextBundleReadiness,
) -> str:
    return hash_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "generated_at": "stable-for-hash",
            "sources": sources,
            "facts": facts,
            "rules": rules,
            "evidence": evidence,
            "readiness": readiness.model_dump(mode="json"),
        }
    )


def _readiness(
    *,
    sources: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    open_unknown_count: int,
    blocking_contradiction_count: int,
) -> ContextBundleReadiness:
    blocking: list[str] = []
    warnings: list[str] = []
    if not sources:
        blocking.append("no_published_sources")
    if not facts and not rules:
        blocking.append("no_published_records")
    if open_unknown_count:
        blocking.append("open_unknown_items")
    if blocking_contradiction_count:
        blocking.append("blocking_contradictions")

    source_ids = {str(row["id"]) for row in sources if row.get("id")}
    evidence_ids = {str(row["id"]) for row in evidence if row.get("id")}
    for row in [*facts, *rules]:
        if str(row.get("source_id")) not in source_ids:
            blocking.append("published_record_missing_source")
        if not row.get("source_id") or not row.get("chunk_id"):
            blocking.append("published_record_missing_provenance")
        record_evidence_ids = _referenced_evidence_span_ids([row])
        if not record_evidence_ids or not any(
            evidence_id in evidence_ids for evidence_id in record_evidence_ids
        ):
            warnings.append("published_record_missing_evidence")
        confidence = row.get("confidence")
        if isinstance(confidence, int | float | Decimal) and confidence < LOW_CONFIDENCE_THRESHOLD:
            warnings.append("low_confidence_record")

    blocking = sorted(set(blocking))
    warnings = sorted(set(warnings))
    score = max(0, min(100, 100 - len(blocking) * 25 - len(warnings) * 5))
    status: Literal["ready", "warning", "blocked"]
    status = "blocked" if blocking else "warning" if warnings else "ready"
    return ContextBundleReadiness(
        status=status,
        score=score,
        blocking_reasons=blocking,
        warnings=warnings,
    )


def _with_evidence_ids(
    row: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    available_ids = {str(item["id"]) for item in evidence if item.get("id")}
    evidence_span_ids = [
        evidence_span_id
        for evidence_span_id in _referenced_evidence_span_ids([row])
        if evidence_span_id in available_ids
    ]
    return {**row, "evidence_span_ids": evidence_span_ids}


def _load_evidence(
    db: Client,
    *,
    workspace_id: str,
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_span_ids = _referenced_evidence_span_ids([*facts, *rules])
    if not evidence_span_ids:
        return []
    return [
        _safe_evidence_row(row)
        for row in _rows(
        db.table("evidence_spans")
        .select("id,source_id,chunk_id,quote,page_number,sheet_name,row_number")
        .eq("workspace_id", workspace_id)
        .in_("id", evidence_span_ids)
        .execute()
        .data
        )
    ]


def _referenced_evidence_span_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    evidence_span_ids: list[str] = []
    for row in rows:
        candidates: list[Any] = []
        if row.get("evidence_span_id") is not None:
            candidates.append(row.get("evidence_span_id"))
        if isinstance(row.get("evidence_span_ids"), list):
            candidates.extend(row["evidence_span_ids"])
        for candidate in candidates:
            evidence_span_id = str(candidate)
            if evidence_span_id not in seen:
                seen.add(evidence_span_id)
                evidence_span_ids.append(evidence_span_id)
    return evidence_span_ids


def _safe_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "quote": _safe_bundle_quote(row.get("quote"))}


def _safe_bundle_quote(value: Any) -> str | None:
    quote = safe_quote(value, user_role=BUNDLE_QUOTE_ROLE)
    if quote is None:
        return None
    if _looks_private_string(quote):
        return None
    return quote


def _safe_record_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "normalized_content": _safe_payload(row.get("normalized_content")),
        "condition": _safe_payload(row.get("condition")),
        "action": _safe_payload(row.get("action")),
    }


def _safe_payload(value: Any) -> Any:
    return _strip_private_strings(redact_sensitive(value))


def _strip_private_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_private_strings(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_strip_private_strings(item) for item in value]
    if isinstance(value, str) and _looks_private_string(value):
        return None
    return value


def _looks_private_string(value: str) -> bool:
    lowered = value.lower()
    if "traceback (most recent call last)" in lowered:
        return True
    if any(marker in lowered for marker in ("x-amz-signature=", "password=")):
        return True
    if any(marker in lowered for marker in ("raw_prompt", "raw prompt", "provider_response")):
        return True
    return any(pattern.search(value) for pattern in PRIVATE_QUOTE_PATTERNS)


def _referenced_evidence_rows(
    evidence: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    referenced_ids = set(_referenced_evidence_span_ids([*facts, *rules]))
    return [
        row
        for row in evidence
        if row.get("id") is not None and str(row["id"]) in referenced_ids
    ]


def _published_or_statusless_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("status") is None or row.get("status") == "published"
    ]


def _audit_export(
    db: Client,
    *,
    bundle: ContextBundleResponse,
    actor_user_id: str,
    actor_role: str,
) -> None:
    insert_row(
        db,
        "audit_logs",
        {
            "workspace_id": str(bundle.workspace_id),
            "actor_user_id": actor_user_id,
            "action": "context_bundle.export",
            "resource_type": "context_bundle",
            "resource_id": None,
            "input_hash": hash_payload(
                {
                    "workspace_id": str(bundle.workspace_id),
                    "actor_user_id": actor_user_id,
                    "actor_role": actor_role,
                }
            ),
            "output_hash": bundle.integrity.bundle_hash,
            "metadata": {
                "schema_version": bundle.schema_version,
                "context_version": bundle.context_version,
                "readiness_status": bundle.readiness.status,
                "source_count": bundle.integrity.source_count,
                "fact_count": bundle.integrity.fact_count,
                "rule_count": bundle.integrity.rule_count,
                "evidence_count": bundle.integrity.evidence_count,
            },
        },
    )


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get("id", "")))


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _count(result: Any) -> int:
    count = getattr(result, "count", None)
    if count is not None:
        return int(count)
    return len(_rows(getattr(result, "data", None)))
