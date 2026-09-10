from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class GscConnectUrlOut(BaseModel):
    authorization_url: str


class GscPropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    site_url: str
    permission_level: str
    selected: bool


class GscSelectPropertyRequest(BaseModel):
    project_id: uuid.UUID | None = None


class GscSyncResultOut(BaseModel):
    synced: int
    failed: int
    total: int


class GscQueryRowOut(BaseModel):
    query: str | None = None
    page: str | None = None
    clicks: int
    impressions: int
    ctr: float
    position: float
