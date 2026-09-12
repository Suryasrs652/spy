"""§50-§52 opportunity engine — priority scoring and the Action Center
buckets it feeds.

The regression these guard: for the whole life of the engine up to now,
`priority_score` was normalized against an effort of 1 that no category has,
so nothing could score above 50. DO_NOW (>=60) and THIS_WEEK (>=40) were
unreachable, and every audit filed every single finding under THIS_MONTH or
MONITOR. The bug was invisible from inside the engine — the numbers were
consistent, just compressed into the bottom half of their own scale.
"""
from __future__ import annotations

import uuid

from app.modules.recommendations.engine import (
    _CATEGORY_EFFORT,
    _SEVERITY_IMPACT,
    build_recommendations,
)
from app.modules.seo.models import Severity
from app.modules.seo.rules.base import CERTAIN, RuleFinding


def _worst_case_finding(category: str) -> RuleFinding:
    """The most urgent thing the formula can describe: a certainty of the
    highest severity, affecting every page of the site."""
    return RuleFinding(
        "SEO_TEST_001", category, Severity.CRITICAL,
        "Title", "Description", "Recommendation",
        score_impact=-10.0, confidence=CERTAIN,
        affected=[(uuid.uuid4(), {"url": f"https://example.com/{i}"}) for i in range(10)],
    )


def test_the_top_of_the_scale_is_reachable() -> None:
    cheapest = min(_CATEGORY_EFFORT, key=_CATEGORY_EFFORT.get)
    recs = build_recommendations([_worst_case_finding(cheapest)], total_pages=10)
    assert recs[0]["priority_score"] == 100.0
    assert recs[0]["group"] == "DO_NOW"


def test_every_bucket_can_be_produced() -> None:
    """A four-bucket Action Center with two permanently empty buckets is a
    two-bucket Action Center that lies about it."""
    findings = [
        # Site-wide critical in the cheapest category -> the top of the scale.
        RuleFinding("SEO_A", "Metadata", Severity.CRITICAL, "t", "d", "r",
                    score_impact=-1, affected=[(uuid.uuid4(), {})] * 10),
        RuleFinding("SEO_B", "Metadata", Severity.HIGH, "t", "d", "r",
                    score_impact=-1, affected=[(uuid.uuid4(), {})] * 6),
        RuleFinding("SEO_C", "Content", Severity.HIGH, "t", "d", "r",
                    score_impact=-1, affected=[(uuid.uuid4(), {})] * 8),
        RuleFinding("SEO_D", "Content", Severity.LOW, "t", "d", "r",
                    score_impact=-1, affected=[(uuid.uuid4(), {})]),
    ]
    groups = {r["group"] for r in build_recommendations(findings, total_pages=10)}
    assert groups == {"DO_NOW", "THIS_WEEK", "THIS_MONTH", "MONITOR"}


def test_priority_falls_with_reach() -> None:
    site_wide = build_recommendations([_worst_case_finding("Metadata")], total_pages=10)
    one_page = build_recommendations([_worst_case_finding("Metadata")], total_pages=1000)
    assert site_wide[0]["priority_score"] > one_page[0]["priority_score"]


def test_priority_falls_with_effort() -> None:
    cheap = build_recommendations([_worst_case_finding("Metadata")], total_pages=10)
    dear = build_recommendations([_worst_case_finding("Content")], total_pages=10)
    assert _CATEGORY_EFFORT["Content"] > _CATEGORY_EFFORT["Metadata"]
    assert cheap[0]["priority_score"] > dear[0]["priority_score"]


def test_severity_drives_impact() -> None:
    assert _SEVERITY_IMPACT["CRITICAL"] > _SEVERITY_IMPACT["INFO"]
    critical = build_recommendations([_worst_case_finding("Metadata")], total_pages=10)
    info = _worst_case_finding("Metadata")
    info.severity = Severity.INFO
    assert critical[0]["priority_score"] > build_recommendations([info], total_pages=10)[0]["priority_score"]


def test_findings_with_no_affected_pages_are_dropped() -> None:
    empty = RuleFinding("SEO_EMPTY", "Metadata", Severity.HIGH, "t", "d", "r", score_impact=0)
    assert build_recommendations([empty], total_pages=10) == []
