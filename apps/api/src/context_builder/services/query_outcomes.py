from __future__ import annotations

from typing import Any

from context_builder.services.query_answer_renderer import (
    build_valid_answer,
)
from context_builder.services.query_budget import (
    fit_budget,
)
from context_builder.services.query_evidence import (
    EvidenceSpanLoader,
    build_evidence_for_outcome,
)
from context_builder.services.query_response_builder import QueryOutcome

_NOT_FOUND_ANSWER = "Nao encontrei essa informacao nas fontes validadas."
_NEEDS_HUMAN_ANSWER = (
    "Existe informacao relacionada, mas ela ainda nao foi validada por revisao humana."
)
_CONFLICTING_ANSWER = (
    "Encontrei fontes publicadas conflitantes. E necessario resolver o conflito antes de responder."
)


def build_conflicting_outcome(
    contradictions: list[dict[str, Any]],
    *,
    published_facts: list[dict[str, Any]],
    published_rules: list[dict[str, Any]],
) -> QueryOutcome:
    sources_used = source_ids_from_contradictions(contradictions) or collect_source_ids(
        published_facts + published_rules
    )
    return QueryOutcome(
        answer_state="conflicting_sources",
        answer=_CONFLICTING_ANSWER,
        confidence=0.0,
        facts=[],
        rules=[],
        sources_used=sources_used,
        evidence=[],
        missing_data=[],
        warnings=["conflict_requires_review"],
        context_pack_tokens_estimated=0,
    )


def build_valid_or_partial_outcome(
    *,
    sources_by_id: dict[str, dict[str, Any]],
    published_facts: list[dict[str, Any]],
    published_rules: list[dict[str, Any]],
    context_budget_tokens: int,
    user_role: str,
    include_evidence: bool,
    evidence_span_loader: EvidenceSpanLoader,
) -> QueryOutcome:
    visible_facts, fact_tokens = fit_budget(
        published_facts,
        budget_tokens=context_budget_tokens,
        user_role=user_role,
    )
    remaining_budget = max(0, context_budget_tokens - fact_tokens)
    visible_rules, rule_tokens = fit_budget(
        published_rules,
        budget_tokens=remaining_budget,
        user_role=user_role,
    )
    facts = visible_facts
    rules = visible_rules
    if not facts and not rules:
        answer_state = "partial_answer"
        answer = "Encontrei apenas parte da informacao nas fontes validadas."
        missing_data = ["context_budget"]
    else:
        answer_state = "valid_answer"
        answer = build_valid_answer(facts, rules)
        missing_data = []

    evidence = build_evidence_for_outcome(
        facts=facts,
        rules=rules,
        sources_by_id=sources_by_id,
        user_role=user_role,
        include_evidence=include_evidence,
        evidence_span_loader=evidence_span_loader,
    )

    return QueryOutcome(
        answer_state=answer_state,
        answer=answer,
        confidence=max(
            [float(row["confidence"]) for row in facts + rules if row.get("confidence") is not None],
            default=0.0,
        ),
        facts=facts,
        rules=rules,
        sources_used=collect_source_ids(facts + rules),
        evidence=evidence,
        missing_data=missing_data,
        warnings=[],
        context_pack_tokens_estimated=min(context_budget_tokens, fact_tokens + rule_tokens),
    )


def build_needs_human_validation_outcome() -> QueryOutcome:
    return QueryOutcome(
        answer_state="needs_human_validation",
        answer=_NEEDS_HUMAN_ANSWER,
        confidence=0.0,
        facts=[],
        rules=[],
        sources_used=[],
        evidence=[],
        missing_data=["human_validation"],
        warnings=[],
        context_pack_tokens_estimated=0,
    )


def build_not_found_outcome() -> QueryOutcome:
    return QueryOutcome(
        answer_state="not_found",
        answer=_NOT_FOUND_ANSWER,
        confidence=0.0,
        facts=[],
        rules=[],
        sources_used=[],
        evidence=[],
        missing_data=["published_data"],
        warnings=[],
        context_pack_tokens_estimated=0,
    )


def collect_source_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        source_id = row.get("source_id")
        if isinstance(source_id, str) and source_id not in seen:
            seen.add(source_id)
            ordered.append(source_id)
    return ordered


def source_ids_from_contradictions(contradictions: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for contradiction in contradictions:
        for source_id in contradiction.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id not in seen:
                seen.add(source_id)
                ordered.append(source_id)
    return ordered

