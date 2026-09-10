"""§21/§22 Spy Score, plus the §48/§49 AEO/GEO reduced deterministic subset.

Pure function of stored crawl evidence + rule findings — no re-fetching, no
LLM guessing (§3). Every audit stores the `score_version` it was computed
under (`CURRENT_SCORE_VERSION`); a later change to weights or formulas ships
under a new version string and never mutates a completed audit's score
(§22, §132).

Authority has no data source in M1 (backlinks ship in M1.2 per the roadmap)
so it is reported as unavailable rather than a manufactured guess — its
weight is proportionally redistributed across the components that *do* have
real evidence, per §3's "never manufacture certainty" principle. AEO/GEO use
a reduced signal set (schema presence/type, heading structure) rather than
the full §48/§49 checklists — documented in the docstrings below, not
claimed as complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.crawler.models import CrawlPage
from app.modules.seo.rules import RuleFinding

CURRENT_SCORE_VERSION = "spy-score-v1.0"

# §21 composition. "authority" is included for documentation even though
# M1 has no data source for it; see _redistribute_weights.
COMPONENT_WEIGHTS = {
    "technical": 0.20,
    "onpage": 0.15,
    "content": 0.15,
    "performance": 0.10,
    "architecture": 0.10,
    "authority": 0.10,
    "aeo": 0.10,
    "geo": 0.10,
}

_SEVERITY_DEDUCTION = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3, "INFO": 0}

_TECHNICAL_CATEGORIES = {"Crawlability", "Indexability", "Security"}
_ONPAGE_CATEGORIES = {"Metadata", "Images", "Structured Data"}
_CONTENT_CATEGORIES = {"Content"}
_ARCHITECTURE_CATEGORIES = {"Links"}


@dataclass
class ScoreBreakdown:
    spy_score: float
    technical_score: float
    seo_score: float
    content_score: float
    performance_score: float
    authority_score: float | None
    aeo_score: float
    geo_score: float
    confidence: float
    score_version: str = CURRENT_SCORE_VERSION
    evidence: dict = field(default_factory=dict)


def _category_score(findings: list[RuleFinding], categories: set[str], total_pages: int) -> float:
    if total_pages == 0:
        return 0.0
    deduction = 0.0
    for f in findings:
        if f.category not in categories:
            continue
        weight = _SEVERITY_DEDUCTION.get(f.severity.value, 0)
        deduction += weight * (f.affected_count / total_pages)
    return round(max(0.0, 100.0 - deduction), 2)


def _performance_score(pages: list[CrawlPage]) -> float:
    timed = [p.response_ms for p in pages if p.response_ms is not None]
    if not timed:
        return 50.0  # no timing evidence collected — neutral, not a guess at "good"
    avg_ms = sum(timed) / len(timed)
    if avg_ms <= 500:
        return 100.0
    if avg_ms >= 5000:
        return 0.0
    return round(100.0 - ((avg_ms - 500) / (5000 - 500)) * 100.0, 2)


def _aeo_score(pages: list[CrawlPage]) -> tuple[float, dict]:
    """§48 reduced subset: schema coverage, FAQ-schema presence, and
    heading-hierarchy cleanliness (one H1 per page). Full §48 (direct-answer
    quality, citation readability, author/org bylines) needs content-quality
    signals this crawler doesn't extract yet.
    """
    indexable = [p for p in pages if p.indexable]
    if not indexable:
        return 0.0, {"reason": "no indexable pages"}

    schema_coverage_pct = 100 * sum(1 for p in indexable if p.has_schema) / len(indexable)
    clean_heading_pct = 100 * sum(1 for p in indexable if p.h1_count == 1) / len(indexable)
    has_faq_schema = any("FAQPage" in (p.schema_types or []) for p in pages)

    score = 0.4 * schema_coverage_pct + 0.3 * clean_heading_pct + 0.3 * (100 if has_faq_schema else 40)
    return round(score, 2), {
        "schema_coverage_pct": round(schema_coverage_pct, 1),
        "clean_heading_pct": round(clean_heading_pct, 1),
        "has_faq_schema": has_faq_schema,
    }


def _geo_score(pages: list[CrawlPage]) -> tuple[float, dict]:
    """§49 reduced subset: Organization-entity clarity and machine-readable
    structure (schema presence). Full §49 (topical coverage, original
    evidence, citation readiness) needs content-topic modeling out of scope
    for M1.
    """
    indexable = [p for p in pages if p.indexable]
    if not indexable:
        return 0.0, {"reason": "no indexable pages"}

    has_org_schema = any("Organization" in (p.schema_types or []) for p in pages)
    schema_coverage_pct = 100 * sum(1 for p in indexable if p.has_schema) / len(indexable)

    score = 0.5 * (100 if has_org_schema else 30) + 0.5 * schema_coverage_pct
    return round(score, 2), {
        "has_organization_schema": has_org_schema,
        "schema_coverage_pct": round(schema_coverage_pct, 1),
    }


def _redistribute_weights(available: dict[str, float | None]) -> dict[str, float]:
    """Drop components with no data (currently just `authority` in M1) and
    scale the remaining weights back up to sum to 1.0, rather than silently
    treating a missing component as a zero (which would unfairly tank the
    overall score for something the audit never measured).
    """
    present = {k: w for k, w in COMPONENT_WEIGHTS.items() if available.get(k) is not None}
    total = sum(present.values())
    return {k: w / total for k, w in present.items()}


def compute_spy_score(
    *, pages: list[CrawlPage], findings: list[RuleFinding], urls_processed: int, target_sample_size: int = 20
) -> ScoreBreakdown:
    total_pages = len([p for p in pages if p.status_code is not None]) or 1

    technical = _category_score(findings, _TECHNICAL_CATEGORIES, total_pages)
    seo = _category_score(findings, _ONPAGE_CATEGORIES, total_pages)
    content = _category_score(findings, _CONTENT_CATEGORIES, total_pages)
    architecture = _category_score(findings, _ARCHITECTURE_CATEGORIES, total_pages)
    performance = _performance_score(pages)
    authority: float | None = None  # no backlink data source until M1.2
    aeo, aeo_evidence = _aeo_score(pages)
    geo, geo_evidence = _geo_score(pages)

    # "architecture" (internal linking/orphans/depth, §21's "Internal
    # architecture" weight) contributes to the composite but has no
    # dedicated Audit column — the dashboard doesn't show it as its own
    # card (§20 only lists Spy/SEO/Technical/Content/Performance/Authority/
    # AEO/GEO) — so it lives in `evidence` for anyone who wants the detail.
    components = {
        "technical": technical, "onpage": seo, "content": content,
        "performance": performance, "architecture": architecture,
        "authority": authority, "aeo": aeo, "geo": geo,
    }
    weights = _redistribute_weights(components)
    spy_score = round(sum(components[k] * w for k, w in weights.items()), 2)

    confidence = round(100 * min(1.0, urls_processed / target_sample_size), 2)

    return ScoreBreakdown(
        spy_score=spy_score,
        technical_score=technical,
        seo_score=seo,
        content_score=content,
        performance_score=performance,
        authority_score=authority,
        aeo_score=aeo,
        geo_score=geo,
        confidence=confidence,
        evidence={
            "weights_used": weights,
            "architecture_score": architecture,
            "aeo": aeo_evidence,
            "geo": geo_evidence,
            "total_pages_scored": total_pages,
            "urls_processed": urls_processed,
        },
    )
