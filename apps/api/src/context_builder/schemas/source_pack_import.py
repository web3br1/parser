from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ImportRunStatus = Literal["preflighted", "compiled", "rejected", "failed"]
RecommendedAction = Literal["compile_as_source_pack", "normal_ingest", "reject"]
ReadinessStatus = Literal["ready", "warning", "blocked"]


class SourcePackImportRunCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    workspace_id: str
    input_hash: str
    status: ImportRunStatus
    recommended_action: RecommendedAction
    actor_user_id: str | None = None
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    source_dir: str | None = None
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: ReadinessStatus | None = None
    readiness_score: int | None = Field(default=None, ge=0, le=100)
    numbered_source_count: int = Field(default=0, ge=0)
    csv_count: int = Field(default=0, ge=0)
    markdown_count: int = Field(default=0, ge=0)
    manifest_document_count: int = Field(default=0, ge=0)
    official_reference_count: int = Field(default=0, ge=0)
    missing_files: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePackImportRunUpdate(BaseModel):
    model_config = ConfigDict(strict=True)

    status: ImportRunStatus
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: ReadinessStatus | None = None
    readiness_score: int | None = Field(default=None, ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePackImportRunResponse(SourcePackImportRunCreate):
    id: str
    created_at: str
    updated_at: str
