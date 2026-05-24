from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContextBundleSource(BaseModel):
    id: UUID
    title: str | None = None
    original_filename: str | None = None
    type: str
    source_reliability: str | None = None
    authority_level: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContextBundleFact(BaseModel):
    id: UUID
    fact_type: str
    schema_version: str
    normalized_content: dict[str, Any]
    confidence: float | None = None
    source_id: UUID
    chunk_id: UUID
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    published_at: datetime | None = None


class ContextBundleRule(BaseModel):
    id: UUID
    rule_type: str
    schema_version: str
    condition: dict[str, Any]
    action: dict[str, Any]
    priority: int
    confidence: float | None = None
    source_id: UUID
    chunk_id: UUID
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    published_at: datetime | None = None


class ContextBundleEvidence(BaseModel):
    id: UUID
    source_id: UUID
    chunk_id: UUID | None = None
    quote: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None


class ContextBundleReadiness(BaseModel):
    status: Literal["ready", "warning", "blocked"]
    score: int
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextBundleIntegrity(BaseModel):
    bundle_hash: str
    canonicalization: str = "json.sort_keys.compact.v1"
    source_count: int
    fact_count: int
    rule_count: int
    evidence_count: int


class ContextBundleResponse(BaseModel):
    schema_version: Literal["context_bundle.v1"]
    context_version: str
    workspace_id: UUID
    generated_at: datetime
    sources: list[ContextBundleSource]
    facts: list[ContextBundleFact]
    rules: list[ContextBundleRule]
    evidence: list[ContextBundleEvidence]
    readiness: ContextBundleReadiness
    integrity: ContextBundleIntegrity
