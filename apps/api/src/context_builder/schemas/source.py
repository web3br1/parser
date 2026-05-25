from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SourceResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    workspace_id: str
    status: str
    title: str | None
    original_filename: str | None
    mime_type: str | None
    file_size_bytes: int | None
    created_at: datetime


class UploadResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    source_id: str
    job_id: str
    status: str
    message: str


class SourcePackPreflightRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    source_dir: str
    persist: bool = False


class SourcePackPreflightResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    is_source_pack: bool
    status: Literal["complete", "incomplete", "not_source_pack", "invalid"]
    recommended_action: Literal["compile_as_source_pack", "normal_ingest", "reject"]
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    language: str | None = None
    publication_status: str | None = None
    numbered_source_count: int = 0
    csv_count: int = 0
    markdown_count: int = 0
    manifest_document_count: int = 0
    official_reference_count: int = 0
    readme_present: bool = False
    missing_files: list[str]
    extra_files: list[str]
    errors: list[str]
    import_run_id: str | None = None
