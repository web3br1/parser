from datetime import datetime

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
