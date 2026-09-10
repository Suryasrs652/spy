from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(description="Any URL on the target site, e.g. https://example.com")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str
    canonical_origin: str
    status: str


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None
