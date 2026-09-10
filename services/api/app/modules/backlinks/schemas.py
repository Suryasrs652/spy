from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacklinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_url: str
    source_domain: str
    target_url: str
    anchor_text: str | None
    nofollow: bool
    created_at: datetime
    updated_at: datetime


class BacklinkSummaryOut(BaseModel):
    domain: str
    total_backlinks: int
    referring_domains: int
    followed_backlinks: int
