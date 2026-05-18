from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryOutcome:
    answer_state: str
    answer: str
    confidence: float
    facts: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    sources_used: list[str]
    evidence: list[dict[str, Any]]
    missing_data: list[str]
    warnings: list[str]
    context_pack_tokens_estimated: int


def estimate_text_tokens(value: str) -> int:
    return max(1, (len(value) + 3) // 4)


def apply_output_budget(
    answer: str,
    warnings: list[str],
    max_output_tokens: int | None,
) -> tuple[str, list[str], int]:
    final_answer, output_truncated = _fit_text_budget(answer, max_output_tokens)
    final_warnings = list(warnings)
    if output_truncated:
        final_warnings.append("output_truncated")
    return final_answer, final_warnings, estimate_text_tokens(final_answer)


def build_usage(
    *,
    settings: Any,
    context_budget_tokens: int,
    context_pack_tokens_estimated: int,
    token_input: int,
    token_output: int,
) -> dict[str, Any]:
    return {
        "model_provider": None,
        "model_name": None,
        "model_context_limit_tokens": settings.query_model_context_limit_tokens,
        "context_budget_tokens": context_budget_tokens,
        "context_pack_tokens_estimated": context_pack_tokens_estimated,
        "input_tokens": token_input,
        "output_tokens": token_output,
        "estimated_cost": 0.0,
    }


def build_query_response(
    *,
    audit_id: str,
    answer_state: str,
    answer: str,
    confidence: float,
    facts_used: Sequence[str],
    rules_used: Sequence[str],
    sources_used: Sequence[str],
    evidence: list[dict[str, Any]],
    missing_data: Sequence[str],
    warnings: Sequence[str],
    usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "audit_id": audit_id,
        "answer_state": answer_state,
        "answer": answer,
        "confidence": confidence,
        "used_unvalidated_data": False,
        "facts_used": list(facts_used),
        "rules_used": list(rules_used),
        "sources_used": list(sources_used),
        "evidence": evidence,
        "missing_data": list(missing_data),
        "warnings": list(warnings),
        "usage": usage,
    }


def _fit_text_budget(value: str, max_tokens: int | None) -> tuple[str, bool]:
    if max_tokens is None or estimate_text_tokens(value) <= max_tokens:
        return value, False
    if max_tokens <= 1:
        return value[:4], True
    max_chars = max_tokens * 4
    return value[: max(0, max_chars - 3)].rstrip() + "...", True


def estimate_json_tokens(value: Any) -> int:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return max(1, (len(encoded) + 3) // 4)
