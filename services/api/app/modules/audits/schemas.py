from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditCreateRequest(BaseModel):
    project_id: uuid.UUID
    max_urls: int | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    max_urls: int
    spy_score: float | None = None
    technical_score: float | None = None
    seo_score: float | None = None
    content_score: float | None = None
    performance_score: float | None = None
    authority_score: float | None = None
    aeo_score: float | None = None
    geo_score: float | None = None
    acrs_score: float | None = None
    confidence: float | None = None
    score_version: str
    evidence: dict = {}
    failure_category: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class AuditProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    progress: int
    urls_discovered: int
    urls_processed: int
    heartbeat_at: datetime | None = None
    error_code: str | None = None
    error_detail: str | None = None


class AuditIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: str
    category: str
    severity: str
    title: str
    description: str
    recommendation: str
    affected_count: int
    score_impact: float


class AuditPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    normalized_url: str
    status_code: int | None
    title: str | None
    meta_description: str | None
    h1: str | None
    canonical_url: str | None
    indexable: bool
    word_count: int | None
    crawl_depth: int
    internal_pagerank: float | None = None

    # §144 Site Explorer (technical inventory)
    response_ms: int | None = None
    redirect_count: int = 0
    robots_allowed: bool = True
    from_sitemap: bool = False

    # §144 Content Explorer (content-quality signals)
    h1_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    heading_order_valid: bool = True
    has_schema: bool = False
    schema_types: list[str] = []
    question_heading_count: int = 0
    list_count: int = 0
    table_count: int = 0
    has_definition_list: bool = False
    has_author_byline: bool = False
    images_missing_alt: int = 0


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    title: str
    description: str
    impact: int
    confidence: int
    effort: int
    priority_score: float
    status: str
    group: str


class ScoreDeltaOut(BaseModel):
    baseline: float | None
    current: float | None
    delta: float | None


class IssueSummaryOut(BaseModel):
    rule_id: str
    category: str
    severity: str
    title: str
    affected_count: int


class AuditComparisonOut(BaseModel):
    """§133 — a diff between two COMPLETED audits of the same project,
    always oriented chronologically (`baseline` is the earlier of the two
    audit ids passed in, regardless of which one the caller names first).
    """

    baseline_audit_id: uuid.UUID
    current_audit_id: uuid.UUID
    baseline_created_at: datetime
    current_created_at: datetime
    score_deltas: dict[str, ScoreDeltaOut]
    new_issues: list[IssueSummaryOut]
    resolved_issues: list[IssueSummaryOut]
    persisting_issues: list[IssueSummaryOut]
    page_count_baseline: int
    page_count_current: int
