from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.states import ChunkState, FactState, SourceState


@dataclass(frozen=True)
class Source:
    id: UUID
    workspace_id: UUID
    status: SourceState
    title: str | None = None


@dataclass(frozen=True)
class Chunk:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    status: ChunkState
    content: str
    chunk_index: int


@dataclass(frozen=True)
class Fact:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    chunk_id: UUID
    fact_type: str
    schema_version: str
    content: dict[str, Any]
    status: FactState


@dataclass(frozen=True)
class Rule:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    chunk_id: UUID
    rule_type: str
    schema_version: str
    condition: dict[str, Any]
    action: dict[str, Any]
    status: FactState


@dataclass(frozen=True)
class Unknown:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    chunk_id: UUID
    raw_text: str
    created_at: datetime
