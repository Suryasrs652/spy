from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrackedKeywordCreate(BaseModel):
    keyword: str


class TrackedKeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    keyword: str
    created_at: datetime


class RankOverviewRowOut(BaseModel):
    id: uuid.UUID
    keyword: str
    added_at: datetime
    has_data: bool
    current_position: float | None = None
    best_position: float | None = None


class RankHistoryPointOut(BaseModel):
    date: str
    position: float
    clicks: int
    impressions: int


class RankHistoryOut(BaseModel):
    keyword: str
    has_data: bool
    reason: str | None = None
    current_position: float | None = None
    best_position: float | None = None
    history: list[RankHistoryPointOut]
