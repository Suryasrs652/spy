from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class GscConnectUrlOut(BaseModel):
    authorization_url: str


class GscPropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_url: str
    permission_level: str
    selected: bool
