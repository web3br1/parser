from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["answer"] = "answer"
    max_output_tokens: int | None = Field(default=None, ge=64, le=1200)
    include_evidence: bool = True


class QueryEvidence(BaseModel):
    source_id: str | None
    source_name: str | None = None
    evidence_span_id: str | None = None
    quote: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    chunk_id: str | None
    fact_id: str | None = None
    rule_id: str | None = None


class QueryUsage(BaseModel):
    model_provider: str | None
    model_name: str | None
    model_context_limit_tokens: int | None
    context_budget_tokens: int
    context_pack_tokens_estimated: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class QueryResponse(BaseModel):
    audit_id: UUID | str
    answer_state: Literal[
        "valid_answer",
        "not_found",
        "conflicting_sources",
        "needs_human_validation",
        "partial_answer",
    ]
    answer: str
    confidence: float = Field(..., ge=0, le=1)
    used_unvalidated_data: bool
    facts_used: list[str]
    rules_used: list[str]
    sources_used: list[str]
    evidence: list[QueryEvidence]
    missing_data: list[str]
    warnings: list[str]
    usage: QueryUsage
