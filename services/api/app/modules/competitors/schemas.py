from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompetitorCreate(BaseModel):
    name: str
    url: str


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str
    status: str
    last_crawled_at: datetime | None
    failure_message: str | None
    spy_score: float | None
    seo_score: float | None
    aeo_score: float | None
    geo_score: float | None
    technical_score: float | None
    onpage_score: float | None = None
    content_score: float | None
    performance_score: float | None
    created_at: datetime


class ScoreComparisonOut(BaseModel):
    field: str
    your_score: float | None
    competitor_score: float | None
    delta: float | None


class CompetitorComparisonOut(BaseModel):
    competitor: CompetitorOut
    your_latest_audit_id: uuid.UUID | None
    comparisons: list[ScoreComparisonOut]


class ContentGapOut(BaseModel):
    has_data: bool
    reason: str | None = None
    your_terms: list[str] = []
    competitor_terms: list[str] = []
    gap_terms: list[str] = []
    methodology: str | None = None
