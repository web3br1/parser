from __future__ import annotations

from typing import Any

from context_builder.config import get_settings
from context_builder.services.query_audit import (
    context_pack_hash as _context_pack_hash,
)
from context_builder.services.query_audit import (
    hash_payload,
)
from context_builder.services.query_audit import (
    new_query_audit_id as _new_query_audit_id,
)
from context_builder.services.query_audit import (
    persist_query_audit as _persist_query_audit,
)
from context_builder.services.query_outcomes import (
    build_conflicting_outcome as _build_conflicting_outcome,
)
from context_builder.services.query_outcomes import (
    build_needs_human_validation_outcome as _build_needs_human_validation_outcome,
)
from context_builder.services.query_outcomes import (
    build_not_found_outcome as _build_not_found_outcome,
)
from context_builder.services.query_outcomes import (
    build_valid_or_partial_outcome as _build_valid_or_partial_outcome,
)
from context_builder.services.query_response_builder import (
    apply_output_budget as _apply_output_budget,
)
from context_builder.services.query_response_builder import (
    build_query_response as _build_query_response,
)
from context_builder.services.query_response_builder import (
    build_usage as _build_usage,
)
from context_builder.services.query_response_builder import (
    estimate_text_tokens as _estimate_text_tokens,
)
from context_builder.services.query_retrieval import (
    RANKING_STRATEGY,
    load_published_context,
    open_relevant_contradictions,
)
from context_builder.services.query_retrieval import (
    has_pending_data as _has_pending_data,
)
from context_builder.services.query_retrieval import (
    index_by_id as _index_by_id,
)
from context_builder.services.query_retrieval import (
    query_evidence_spans as _query_evidence_spans,
)
from supabase import Client

_hash_payload = hash_payload

def answer_query(
    db: Client,
    *,
    workspace_id: str,
    question: str,
    actor_user_id: str,
    user_role: str = "staff",
    max_output_tokens: int | None = None,
    include_evidence: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    context_budget_tokens = settings.query_context_budget_tokens

    published_context = load_published_context(
        db,
        workspace_id=workspace_id,
        question=question,
        max_candidate_facts=settings.query_max_candidate_facts,
        max_candidate_rules=settings.query_max_candidate_rules,
    )
    sources_by_id = _index_by_id(published_context.sources)

    contradictions = open_relevant_contradictions(
        db,
        workspace_id=workspace_id,
        published_facts=published_context.facts,
        published_rules=published_context.rules,
    )

    if contradictions:
        outcome = _build_conflicting_outcome(
            contradictions,
            published_facts=published_context.facts,
            published_rules=published_context.rules,
        )
    elif published_context.facts or published_context.rules:
        def load_evidence_spans(evidence_span_ids: list[str]) -> list[dict[str, Any]]:
            return _query_evidence_spans(
                db,
                workspace_id=workspace_id,
                evidence_span_ids=evidence_span_ids,
            )

        outcome = _build_valid_or_partial_outcome(
            sources_by_id=sources_by_id,
            published_facts=published_context.facts,
            published_rules=published_context.rules,
            context_budget_tokens=context_budget_tokens,
            user_role=user_role,
            include_evidence=include_evidence,
            evidence_span_loader=load_evidence_spans,
        )
    elif _has_pending_data(db, workspace_id=workspace_id, question=question):
        outcome = _build_needs_human_validation_outcome()
    else:
        outcome = _build_not_found_outcome()

    facts_used = [str(row["id"]) for row in outcome.facts if row.get("id")]
    rules_used = [str(row["id"]) for row in outcome.rules if row.get("id")]
    source_rows_used = [
        sources_by_id[source_id]
        for source_id in outcome.sources_used
        if source_id in sources_by_id
    ]
    context_hash = _context_pack_hash(
        workspace_id=workspace_id,
        question=question,
        facts=outcome.facts,
        rules=outcome.rules,
        sources=source_rows_used,
        evidence=outcome.evidence,
        contradictions=contradictions or None,
    )

    answer, warnings, token_output = _apply_output_budget(
        outcome.answer,
        outcome.warnings,
        max_output_tokens,
    )
    token_input = _estimate_text_tokens(question) + outcome.context_pack_tokens_estimated

    usage = _build_usage(
        settings=settings,
        context_budget_tokens=context_budget_tokens,
        context_pack_tokens_estimated=outcome.context_pack_tokens_estimated,
        token_input=token_input,
        token_output=token_output,
    )
    audit_id = _new_query_audit_id()
    response = _build_query_response(
        audit_id=audit_id,
        answer_state=outcome.answer_state,
        answer=answer,
        confidence=outcome.confidence,
        facts_used=facts_used,
        rules_used=rules_used,
        sources_used=outcome.sources_used,
        evidence=outcome.evidence,
        missing_data=outcome.missing_data,
        warnings=warnings,
        usage=usage,
    )
    _persist_query_audit(
        db,
        audit_id=audit_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        question=question,
        response=response,
        facts_considered=published_context.facts_considered,
        rules_considered=published_context.rules_considered,
        context_budget_tokens=context_budget_tokens,
        context_pack_tokens_estimated=outcome.context_pack_tokens_estimated,
        context_hash=context_hash,
        token_input=token_input,
        token_output=token_output,
        ranking_strategy=RANKING_STRATEGY,
        request_metadata={
            "include_evidence": include_evidence,
            "max_output_tokens": max_output_tokens,
            "user_role": user_role,
        },
    )
    return response
