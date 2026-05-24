from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContextBundleContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextBundleSource(ContextBundleContractModel):
    id: UUID
    title: str | None = None
    original_filename: str | None = None
    type: str
    source_reliability: str | None = None
    authority_level: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContextBundleFact(ContextBundleContractModel):
    id: UUID
    fact_type: str
    schema_version: str
    normalized_content: dict[str, Any]
    confidence: float | None = None
    source_id: UUID
    chunk_id: UUID
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    published_at: datetime | None = None


class ContextBundleRule(ContextBundleContractModel):
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


class ContextBundleEvidence(ContextBundleContractModel):
    id: UUID
    source_id: UUID
    chunk_id: UUID | None = None
    quote: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None


class ContextBundleReadiness(ContextBundleContractModel):
    status: Literal["ready", "warning", "blocked"]
    score: int
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextBundleIdentity(ContextBundleContractModel):
    workspace_name: str | None = None
    summary: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ContextBundleGap(ContextBundleContractModel):
    id: str | None = None
    kind: str | None = None
    description: str | None = None
    severity: str | None = None
    status: str | None = None
    source_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ContextBundleTest(ContextBundleContractModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    prompt: str | None = None
    expected_behavior: str | None = None
    expected_answer_contains: list[str] = Field(default_factory=list)
    forbidden_answer_contains: list[str] = Field(default_factory=list)
    required_fact_ids: list[UUID] = Field(default_factory=list)
    required_rule_ids: list[UUID] = Field(default_factory=list)
    required_evidence_span_ids: list[UUID] = Field(default_factory=list)
    must_not_use_unvalidated_data: bool = True
    critical: bool = False
    assertion: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class ContextBundleMemoryPolicy(ContextBundleContractModel):
    retention: str | None = None
    profile_memory: str | None = None
    conversation_memory: str | None = None
    persist_user_personal_data: bool = False
    store_unvalidated_claims: bool = False
    retention_days: int | None = None
    allowed_memory_scopes: list[str] = Field(default_factory=list)
    deletion_policy: str | None = None
    allowed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    notes: str | None = None


class ContextBundleToolRecommendation(ContextBundleContractModel):
    id: str | None = None
    tool_name: str | None = None
    category: str | None = None
    risk_level: str | None = None
    recommended: bool = True
    allowed_operations: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    input_policy: str | None = None
    output_policy: str | None = None
    reason: str | None = None
    confidence: float | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class ContextBundleIntegrity(ContextBundleContractModel):
    bundle_hash: str
    canonicalization: str = "json.sort_keys.compact.v1"
    source_count: int
    fact_count: int
    rule_count: int
    evidence_count: int
    gap_count: int = 0
    test_count: int = 0
    tool_recommendation_count: int = 0


class ContextBundleResponse(ContextBundleContractModel):
    schema_version: Literal["context_bundle.v1"]
    context_version: str
    workspace_id: UUID
    generated_at: datetime
    sources: list[ContextBundleSource]
    facts: list[ContextBundleFact]
    rules: list[ContextBundleRule]
    evidence: list[ContextBundleEvidence]
    identity: ContextBundleIdentity = Field(default_factory=ContextBundleIdentity)
    gaps: list[ContextBundleGap] = Field(default_factory=list)
    tests: list[ContextBundleTest] = Field(default_factory=list)
    memory_policy: ContextBundleMemoryPolicy = Field(
        default_factory=ContextBundleMemoryPolicy
    )
    tool_recommendations: list[ContextBundleToolRecommendation] = Field(
        default_factory=list
    )
    readiness: ContextBundleReadiness
    integrity: ContextBundleIntegrity
