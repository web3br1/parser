from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    job_id: str
    status: str
    source_id: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    chunks_created: int | None
