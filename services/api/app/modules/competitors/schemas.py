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
    acrs_score: float | None = None
    technical_score: float | None
    onpage_score: float | None = None
    content_score: float | None
    internal_links_score: float | None = None
    structured_data_score: float | None = None
    performance_score: float | None
    score_version: str | None = None
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


class MatrixFactorOut(BaseModel):
    key: str
    label: str
    your_score: float | None
    """Keyed by competitor id. A value of null means that site has no number
    for this factor — not that it scored zero."""
    competitor_scores: dict[str, float | None]
    best_competitor_id: str | None
    gap_to_best: float | None


class AdvantageOut(BaseModel):
    """One signal where competitors measurably lead, with the numbers behind
    it. `finding` states a difference, never a cause — Spy has no ranking data
    for a competitor's site."""

    key: str
    label: str
    your_value: float
    competitor_values: dict[str, float]
    leaders: list[str]
    competitors_ahead: int
    gap: float
    finding: str
    what_to_do: str


class SizeComparisonOut(BaseModel):
    your_pages: int
    competitor_pages: dict[str, int]
    finding: str
    what_to_do: str


class NotComparableOut(BaseModel):
    competitor_id: str
    name: str
    reason: str


class CompetitorMatrixOut(BaseModel):
    has_data: bool
    reason: str | None = None
    your_latest_audit_id: uuid.UUID | None = None
    your_score_version: str | None = None
    competitors: list[CompetitorOut] = []
    factors: list[MatrixFactorOut] = []
    advantages: list[AdvantageOut] = []
    size: SizeComparisonOut | None = None
    not_comparable: list[NotComparableOut] = []
    methodology: str | None = None
