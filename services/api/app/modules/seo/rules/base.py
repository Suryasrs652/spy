"""§23-§25 SEO rule engine — shared types, registry, and the site-wide
`RuleContext` every rule reads from.

Every rule is a pure function of already-persisted crawl evidence
(`CrawlPage`/`PageLink` rows, plus a handful of site-wide facts the crawler
observed once — robots.txt/sitemap presence, external-link-check results)
and versioned thresholds from `rule_config` (§131) — never a re-fetch, never
an LLM guess (§3). A rule returns a single `RuleFinding` aggregating every
affected page (matching the `audit_issues` + `audit_issue_pages` shape,
§69/§70) or `None` if the site has no instances of that issue.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.seo.models import Severity

DEFAULT_THRESHOLDS = {
    "MIN_TITLE_LENGTH": 15,
    "MAX_TITLE_LENGTH": 60,
    "MIN_DESCRIPTION_LENGTH": 50,
    "MAX_DESCRIPTION_LENGTH": 160,
    "THIN_CONTENT_WORD_THRESHOLD": 150,
    "MAX_CRAWL_DEPTH_WARNING": 4,
    "IMAGE_SIZE_WARNING_BYTES": 300_000,
    "MAX_REDIRECT_CHAIN_LENGTH": 3,
    # M2 additions
    "SLOW_RESPONSE_MS": 2000,
    "LARGE_HTML_SIZE_BYTES": 1_500_000,
    "MIN_TEXT_TO_HTML_RATIO": 0.10,
    "LONG_CONTENT_WORD_THRESHOLD": 600,
    "KEYWORD_STUFFING_RATIO": 0.06,
    "MAX_EXTERNAL_LINKS": 100,
    "MAX_INTERNAL_LINKS": 150,
    "MIN_AVG_INTERNAL_LINKS_PER_PAGE": 1.0,
    "MAX_NOFOLLOW_INTERNAL_RATIO": 0.5,
    # M5 addition — §144 internal PageRank (0-100 normalized, top page = 100).
    "MIN_PAGERANK_FOR_SITEMAP_PAGES": 10.0,
}


# How much of what a rule reports is observation, and how much is inference.
#
# A rule that looks for a canonical tag and doesn't find one is certain:
# the tag is absent, and no amount of second-guessing changes that. A rule
# that reports "keyword stuffing" from a word-frequency ratio is not — the
# same ratio comes out of a page that legitimately repeats its own product
# name. Both are worth reporting. Reporting them as equally certain is what
# teaches a reader to distrust the whole audit.
#
# Read it as: of the instances this rule flags, what share would survive a
# human opening the page and looking? Rules declare it only when it is below
# CERTAIN, so the default stays the honest one for the ~80 rules that read a
# fact straight off the page.
#
# It is not severity. Severity is how much the issue costs if real;
# confidence is whether it is real. A low-severity certainty (missing
# favicon) and a high-severity guess (possible anchor over-optimization) are
# different kinds of thing, and the priority formula in
# app/modules/recommendations/engine.py multiplies them for that reason.
CERTAIN = 1.0


@dataclass
class RuleFinding:
    rule_id: str
    category: str
    severity: Severity
    title: str
    description: str
    recommendation: str
    score_impact: float
    confidence: float = CERTAIN
    affected: list[tuple[uuid.UUID, dict]] = field(default_factory=list)

    @property
    def affected_count(self) -> int:
        return len(self.affected)


@dataclass
class RuleContext:
    """Everything a rule can read. `pages`/`links` are the full per-audit
    evidence; `config` is versioned thresholds (§131); `site_facts` and
    `external_link_status` are the handful of site-wide observations the
    crawler makes once rather than per-page (§144 M2).
    """

    pages: list[CrawlPage]
    links: list[PageLink]
    config: dict
    robots_txt_found: bool = True
    robots_disallow_all: bool = False
    sitemap_found: bool = False
    max_urls_reached: bool = False

    def crawled(self) -> list[CrawlPage]:
        """Pages that were actually fetched (excludes robots-blocked
        entries, which never got a status code)."""
        return [p for p in self.pages if p.status_code is not None]

    def indexable(self) -> list[CrawlPage]:
        return [p for p in self.crawled() if p.indexable]

    def total_pages(self) -> int:
        return len(self.crawled()) or 1

    def by_normalized_url(self) -> dict[str, CrawlPage]:
        return {p.normalized_url: p for p in self.pages}

    def inbound_internal_link_counts(self) -> dict[uuid.UUID, int]:
        counts: dict[uuid.UUID, int] = defaultdict(int)
        for link in self.links:
            if link.is_internal and link.target_page_id:
                counts[link.target_page_id] += 1
        return counts

    def outbound_internal_link_counts(self) -> dict[uuid.UUID, int]:
        counts: dict[uuid.UUID, int] = defaultdict(int)
        for link in self.links:
            if link.is_internal and link.source_page_id:
                counts[link.source_page_id] += 1
        return counts


RuleFn = Callable[[RuleContext], "RuleFinding | None"]
_REGISTRY: list[RuleFn] = []


def rule(fn: RuleFn) -> RuleFn:
    _REGISTRY.append(fn)
    return fn


def run_all_rules(
    pages: list[CrawlPage],
    links: list[PageLink],
    rule_config: dict | None = None,
    site_facts: dict | None = None,
) -> list[RuleFinding]:
    facts = site_facts or {}
    ctx = RuleContext(
        pages=pages,
        links=links,
        config={**DEFAULT_THRESHOLDS, **(rule_config or {})},
        robots_txt_found=facts.get("robots_txt_found", True),
        robots_disallow_all=facts.get("robots_disallow_all", False),
        sitemap_found=facts.get("sitemap_found", False),
        max_urls_reached=facts.get("max_urls_reached", False),
    )
    findings = []
    for fn in _REGISTRY:
        result = fn(ctx)
        if result is not None:
            findings.append(result)
    return findings
