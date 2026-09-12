"""§50-§52 opportunity engine — turns rule findings into prioritized,
actionable recommendations.

Priority = Impact × Confidence × Reach / Effort, normalized to 0-100 (§51).
Impact/confidence/effort are derived deterministically from the finding's
own severity and affected-page count — never an LLM guess (§3).
"""
from __future__ import annotations

import uuid

from app.modules.recommendations.models import RecommendationGroup
from app.modules.seo.rules import RuleFinding

_SEVERITY_IMPACT = {"CRITICAL": 10, "HIGH": 8, "MEDIUM": 5, "LOW": 3, "INFO": 1}

# Effort is a rough per-rule-category estimate of how much work fixing one
# instance typically takes (1 = trivial markup change, 10 = structural
# rework) — configurable later via rule_config if this needs to vary by site.
_CATEGORY_EFFORT = {
    "Crawlability": 6, "Indexability": 4, "Metadata": 2, "Content": 7,
    "Links": 4, "Images": 2, "Structured Data": 5, "Security": 6,
    "International": 5,
}

_MIN_EFFORT = min(_CATEGORY_EFFORT.values())

# The ceiling the raw score is normalized against: the most urgent thing the
# formula can describe — a maximum-impact certainty affecting the whole site,
# in the cheapest category there is.
#
# This used to divide by an effort of 1, which no category has. Nothing could
# score above 50 as a result, and since DO_NOW needs 60 and THIS_WEEK needs
# 40, the two buckets a reader actually works from were unreachable: every
# audit ever run here filed everything under THIS_MONTH or MONITOR.
_MAX_RAW_PRIORITY = 10 * 10 * 1.0 / _MIN_EFFORT


def _group_for(priority_score: float, severity: str) -> str:
    if severity in ("CRITICAL", "HIGH") and priority_score >= 60:
        return RecommendationGroup.DO_NOW.value
    if priority_score >= 40:
        return RecommendationGroup.THIS_WEEK.value
    if priority_score >= 15:
        return RecommendationGroup.THIS_MONTH.value
    return RecommendationGroup.MONITOR.value


def build_recommendations(
    findings: list[RuleFinding], *, total_pages: int
) -> list[dict]:
    """Returns plain dicts ready to become `Recommendation` rows — kept as
    dicts (not ORM objects) so this stays a pure, easily-unit-tested
    function with no DB/session dependency.
    """
    total_pages = max(total_pages, 1)
    recommendations: list[dict] = []

    for f in findings:
        if f.affected_count == 0:
            continue

        severity = f.severity.value
        impact = _SEVERITY_IMPACT.get(severity, 1)
        reach = min(1.0, f.affected_count / total_pages)  # 0..1 fraction of the site
        # The rule says how much of its own finding is observation rather
        # than inference (see rules/base.py). Most rules read a fact off the
        # page and score the full 10; a threshold heuristic scores less, and
        # is ranked below a certainty of the same severity and reach. This
        # used to be hardcoded to 10, which ranked "possible keyword
        # stuffing" as confidently as a missing title tag.
        confidence = round(f.confidence * 10)
        effort = _CATEGORY_EFFORT.get(f.category, 5)

        raw_priority = impact * confidence * reach / effort
        priority_score = round(min(100.0, (raw_priority / _MAX_RAW_PRIORITY) * 100.0), 2)

        recommendations.append(
            {
                "id": uuid.uuid4(),
                "category": f.category,
                "title": f.title,
                "description": f.description,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "priority_score": priority_score,
                "status": "OPEN",
                "group": _group_for(priority_score, severity),
                "evidence": {
                    "rule_id": f.rule_id,
                    "severity": severity,
                    "affected_count": f.affected_count,
                    "recommendation": f.recommendation,
                    "sample_urls": [ev.get("url") for _pid, ev in f.affected[:10] if ev.get("url")],
                },
            }
        )

    recommendations.sort(key=lambda r: r["priority_score"], reverse=True)
    return recommendations
