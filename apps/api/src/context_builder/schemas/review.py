from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Requests ────────────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    note: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    note: str | None = None


class EditFactRequest(BaseModel):
    content: dict[str, Any] = Field(...)
    note: str | None = None


class EditRuleRequest(BaseModel):
    condition: dict[str, Any] = Field(...)
    action: dict[str, Any] = Field(...)
    note: str | None = None


class ReclassifyRequest(BaseModel):
    fact_type: str = Field(...)
    destination: str = Field(...)
    note: str | None = None


class IgnoreRequest(BaseModel):
    note: str | None = None


# ── Responses ────────────────────────────────────────────────────────────────

class EvidenceSpanResponse(BaseModel):
    id: UUID
    quote: str
    char_start: int | None
    char_end: int | None
    page_number: int | None
    sheet_name: str | None
    row_number: int | None


class ExtractedFactResponse(BaseModel):
    id: UUID
    fact_type: str
    schema_version: str
    content: dict[str, Any]
    normalized_content: dict[str, Any]
    status: str
    confidence: float | None
    model_name: str | None
    prompt_version: str | None
    evidence_span: EvidenceSpanResponse | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    supersedes: UUID | None
    superseded_by: UUID | None
    created_at: datetime


class BusinessRuleResponse(BaseModel):
    id: UUID
    rule_type: str
    schema_version: str
    condition: dict[str, Any]
    action: dict[str, Any]
    status: str
    confidence: float | None
    model_name: str | None
    prompt_version: str | None
    evidence_span: EvidenceSpanResponse | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    supersedes: UUID | None
    superseded_by: UUID | None
    created_at: datetime


class ChunkReviewItem(BaseModel):
    """Item na fila de revisão — chunk com resumo de pendências."""
    chunk_id: UUID
    source_id: UUID
    source_name: str
    chunk_index: int
    content_preview: str
    facts_total: int
    facts_pending: int
    rules_total: int
    rules_pending: int
    unknown_total: int
    has_ambiguities: bool
    created_at: datetime


class ChunkDetailResponse(BaseModel):
    """Detalhe completo de um chunk para a tela de revisão."""
    chunk_id: UUID
    source_id: UUID
    source_name: str
    chunk_index: int
    content: str
    facts: list[ExtractedFactResponse]
    rules: list[BusinessRuleResponse]


class ReviewQueueResponse(BaseModel):
    items: list[ChunkReviewItem]
    total: int
    page: int
    per_page: int
    pages: int


class ActionResponse(BaseModel):
    """
    Resposta genérica para approve / reject / edit.
    resource_id é o ID do recurso afetado (ou do novo recurso em caso de edit).
    """
    status: str
    resource_id: UUID
    resource_type: str


class UnknownQueueItem(BaseModel):
    id: UUID
    chunk_id: UUID
    source_id: UUID
    raw_text: str
    suggested_fact_type: str | None
    confidence: float | None
    status: str
    resolution: str | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime


class UnknownQueueResponse(BaseModel):
    items: list[UnknownQueueItem]
    total: int
    page: int
    per_page: int
    pages: int


class ReclassifyResponse(BaseModel):
    status: str
    extraction_job_id: str


class IgnoreResponse(BaseModel):
    status: str
