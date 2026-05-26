from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ContextBuildMode = Literal["single_document", "multi_document_batch", "source_pack"]
ContextBuildStatus = Literal[
    "created",
    "preflighted",
    "queued",
    "processing",
    "needs_review",
    "ready_to_export",
    "compiled",
    "rejected",
    "failed",
]
ContextBuildRecommendedAction = Literal[
    "normal_ingest",
    "batch_ingest",
    "compile_as_source_pack",
    "reject",
]
ReadinessStatus = Literal["ready", "warning", "blocked"]


class ContextBuildFileMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    size: int = Field(ge=0)
    relative_path: str | None = None
    mime_type: str | None = None
    type: str | None = None
    last_modified: int | None = None


class ContextBuildPreflightRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    files: list[ContextBuildFileMetadata] = Field(default_factory=list)
    source_dir: str | None = None
    staged_upload_id: str | None = None
    input_fingerprint: str | None = None
    input_hash: str | None = None
    persist: bool = False


class ContextBuildRunCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    input_mode: ContextBuildMode
    input_fingerprint: str
    recommended_action: ContextBuildRecommendedAction
    input_hash: str | None = None
    source_dir: str | None = None
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    staged_upload_id: str | None = None
    source_count: int = Field(default=0, ge=0)
    job_count: int = Field(default=0, ge=0)
    file_counts: dict[str, int] = Field(default_factory=dict)
    missing_files: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBuildCompileRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    confirmed: bool | None = None
    confirmation: bool | None = None


class ContextBuildPreflightResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: str | None = None
    status: ContextBuildStatus
    input_mode: ContextBuildMode
    recommended_action: ContextBuildRecommendedAction
    input_fingerprint: str
    input_hash: str | None = None
    source_dir: str | None = Field(default=None, exclude=True)
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    missing_files: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBuildStagedUploadResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    staged_upload_id: str
    input_hash: str
    input_fingerprint: str
    files: list[ContextBuildFileMetadata] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ContextBuildRunResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    workspace_id: str
    actor_user_id: str | None = None
    input_mode: ContextBuildMode
    status: ContextBuildStatus
    recommended_action: ContextBuildRecommendedAction
    input_fingerprint: str
    input_hash: str | None = None
    source_dir: str | None = Field(default=None, exclude=True)
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    staged_upload_id: str | None = None
    source_count: int = Field(default=0, ge=0)
    job_count: int = Field(default=0, ge=0)
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: ReadinessStatus | None = None
    readiness_score: int | None = Field(default=None, ge=0, le=100)
    file_counts: dict[str, int] = Field(default_factory=dict)
    missing_files: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
