from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PublishedFactRecord(BaseModel):
    kind: str = "fact"
    id: UUID
    fact_type: str
    schema_version: str
    normalized_content: dict[str, Any]
    confidence: float | None
    source_id: UUID
    chunk_id: UUID
    published_at: datetime | None
    reviewed_by: UUID | None


class PublishedRuleRecord(BaseModel):
    kind: str = "rule"
    id: UUID
    rule_type: str
    schema_version: str
    condition: dict[str, Any]
    action: dict[str, Any]
    priority: int
    confidence: float | None
    source_id: UUID
    chunk_id: UUID
    published_at: datetime | None
    reviewed_by: UUID | None


class KnowledgeListResponse(BaseModel):
    items: list[PublishedFactRecord | PublishedRuleRecord]
    total: int
    page: int
    per_page: int
    pages: int
    facts_count: int
    rules_count: int
