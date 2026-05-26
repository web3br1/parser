from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from domain.states import ChunkState, FactState, SourceState


class ContextBuildStatus(StrEnum):
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY_TO_EXPORT = "ready_to_export"
    COMPILED = "compiled"
    REJECTED = "rejected"
    FAILED = "failed"


class ContextBuildMode(StrEnum):
    SINGLE_DOCUMENT = "single_document"
    MULTI_DOCUMENT_BATCH = "multi_document_batch"
    SOURCE_PACK = "source_pack"


class ContextBuildRecommendedAction(StrEnum):
    NORMAL_INGEST = "normal_ingest"
    BATCH_INGEST = "batch_ingest"
    COMPILE_AS_SOURCE_PACK = "compile_as_source_pack"
    REJECT = "reject"


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


@dataclass(frozen=True)
class ContextBuildRun:
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID
    input_mode: ContextBuildMode
    input_fingerprint: str
    input_hash: str | None
    status: ContextBuildStatus
    recommended_action: ContextBuildRecommendedAction | None = None
    bundle_hash: str | None = None
    context_version: str | None = None
    readiness_status: str | None = None
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
        input_mode: ContextBuildMode,
        input_fingerprint: str,
        input_hash: str | None = None,
    ) -> "ContextBuildRun":
        return cls(
            id=id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            input_mode=input_mode,
            input_fingerprint=input_fingerprint,
            input_hash=input_hash,
            status=ContextBuildStatus.CREATED,
        )

    def mark_preflighted(
        self,
        *,
        recommended_action: ContextBuildRecommendedAction,
    ) -> "ContextBuildRun":
        return replace(
            self,
            status=ContextBuildStatus.PREFLIGHTED,
            recommended_action=recommended_action,
        )

    def mark_queued(self) -> "ContextBuildRun":
        return replace(self, status=ContextBuildStatus.QUEUED)

    def mark_processing(self) -> "ContextBuildRun":
        return replace(self, status=ContextBuildStatus.PROCESSING)

    def mark_compiled(
        self,
        *,
        bundle_hash: str,
        context_version: str,
        readiness_status: str,
    ) -> "ContextBuildRun":
        return replace(
            self,
            status=ContextBuildStatus.COMPILED,
            bundle_hash=bundle_hash,
            context_version=context_version,
            readiness_status=readiness_status,
        )

    def mark_failed(self, *, error: str) -> "ContextBuildRun":
        return replace(self, status=ContextBuildStatus.FAILED, error=error)
