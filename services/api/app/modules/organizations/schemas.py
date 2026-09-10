from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
