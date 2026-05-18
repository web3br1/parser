from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    slug: str | None = None


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    name: str
    slug: str | None
    status: str
    created_at: datetime
