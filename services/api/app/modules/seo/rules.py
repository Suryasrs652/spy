"""§23-§25 SEO rule engine.

Every rule is a pure function of already-persisted crawl evidence
(`CrawlPage`/`PageLink` rows) plus versioned thresholds from `rule_config`
(§131) — never a re-fetch, never an LLM guess (§3). A rule returns a single
`RuleFinding` aggregating every affected page (matching the `audit_issues` +
`audit_issue_pages` shape, §69/§70) or `None` if the site has no instances
of that issue.

International/hreflang checks (§23's "International" category) are a known
M1 gap — most audited sites are single-language and the effort was
prioritized toward scoring/AEO/GEO instead; tracked for a later milestone.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
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
}


@dataclass
class RuleFinding:
    rule_id: str
    category: str
    severity: Severity
    title: str
    description: str
    recommendation: str
    score_impact: float
    affected: list[tuple[uuid.UUID, dict]] = field(default_factory=list)

    @property
    def affected_count(self) -> int:
        return len(self.affected)


RuleFn = Callable[[list[CrawlPage], list[PageLink], dict], "RuleFinding | None"]
_REGISTRY: list[RuleFn] = []


def rule(fn: RuleFn) -> RuleFn:
    _REGISTRY.append(fn)
    return fn


def _crawled(pages: list[CrawlPage]) -> list[CrawlPage]:
    """Pages that were actually fetched (excludes robots-blocked entries,
    which never got a status code)."""
    return [p for p in pages if p.status_code is not None]


# ── Crawlability ─────────────────────────────────────────────────────
@rule
def broken_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url, "status_code": p.status_code}) for p in _crawled(pages) if 400 <= p.status_code < 500]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_001", "Crawlability", Severity.HIGH,
        "Broken pages (4xx)",
        "Some crawled URLs return a client-error status code, so visitors and search engines hit a dead end.",
        "Fix the link, restore the page, or 301-redirect it to a working URL.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def server_error_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url, "status_code": p.status_code}) for p in _crawled(pages) if p.status_code >= 500]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_002", "Crawlability", Severity.CRITICAL,
        "Server errors (5xx)",
        "Some pages returned a server error during the crawl, which can get them dropped from the index entirely.",
        "Investigate the server/application error and fix the underlying cause.",
        score_impact=-4 * len(affected), affected=affected,
    )


@rule
def long_redirect_chains(pages, links, cfg) -> RuleFinding | None:
    limit = cfg.get("MAX_REDIRECT_CHAIN_LENGTH", DEFAULT_THRESHOLDS["MAX_REDIRECT_CHAIN_LENGTH"])
    affected = [(p.id, {"url": p.url, "redirect_count": p.redirect_count}) for p in pages if p.redirect_count > limit]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_003", "Crawlability", Severity.MEDIUM,
        "Redirect chains too long",
        f"Some URLs pass through more than {limit} redirects before resolving, wasting crawl budget and link equity.",
        "Point links directly at the final destination URL instead of chaining redirects.",
        score_impact=-1.5 * len(affected), affected=affected,
    )


@rule
def robots_blocked_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in pages if not p.robots_allowed]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_004", "Crawlability", Severity.INFO,
        "Pages blocked by robots.txt",
        "These URLs were discovered but robots.txt disallows crawling them — confirm this is intentional.",
        "Review robots.txt if any of these pages should actually be indexable.",
        score_impact=0, affected=affected,
    )


# ── Indexability ─────────────────────────────────────────────────────
@rule
def noindex_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "robots_meta": p.robots_meta})
        for p in _crawled(pages) if "noindex" in (p.robots_meta or "").lower()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_001", "Indexability", Severity.INFO,
        "Pages marked noindex",
        "These pages tell search engines not to index them — confirm that's deliberate.",
        "Remove the noindex directive from any page that should actually rank.",
        score_impact=0, affected=affected,
    )


@rule
def missing_canonical(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.indexable and not p.canonical_url]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_002", "Indexability", Severity.LOW,
        "Missing canonical tag",
        "These indexable pages have no canonical tag, leaving Google to guess the preferred URL for duplicate content.",
        "Add a self-referencing (or otherwise deliberate) <link rel=\"canonical\"> to each page.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def broken_canonical_target(pages, links, cfg) -> RuleFinding | None:
    by_normalized = {p.normalized_url: p for p in pages}
    affected = []
    for p in _crawled(pages):
        if not p.canonical_url:
            continue
        target = by_normalized.get(p.canonical_url)
        if target is not None and target.status_code and target.status_code >= 400:
            affected.append((p.id, {"url": p.url, "canonical_url": p.canonical_url, "target_status": target.status_code}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_003", "Indexability", Severity.HIGH,
        "Canonical points to a broken page",
        "The canonical tag on these pages points at a URL that itself returns an error.",
        "Point the canonical tag at a working, indexable URL.",
        score_impact=-2 * len(affected), affected=affected,
    )


# ── Metadata ─────────────────────────────────────────────────────────
@rule
def missing_title(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.indexable and not p.title]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_001", "Metadata", Severity.HIGH,
        "Missing title tag",
        "These pages have no <title> tag, which is one of the strongest on-page ranking and CTR signals.",
        "Add one unique, descriptive title tag per page.",
        score_impact=-3 * len(affected), affected=affected,
    )


@rule
def duplicate_titles(pages, links, cfg) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in _crawled(pages):
        if p.indexable and p.title:
            groups[p.title.strip().lower()].append(p)
    affected = [(p.id, {"url": p.url, "title": p.title}) for pages_ in groups.values() if len(pages_) > 1 for p in pages_]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_002", "Metadata", Severity.HIGH,
        "Duplicate title tags",
        "Multiple pages share the exact same title tag, making it harder for search engines to tell them apart.",
        "Write a unique title for each page that reflects its specific content.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def title_length(pages, links, cfg) -> RuleFinding | None:
    min_len = cfg.get("MIN_TITLE_LENGTH", DEFAULT_THRESHOLDS["MIN_TITLE_LENGTH"])
    max_len = cfg.get("MAX_TITLE_LENGTH", DEFAULT_THRESHOLDS["MAX_TITLE_LENGTH"])
    affected = [
        (p.id, {"url": p.url, "title": p.title, "length": len(p.title)})
        for p in _crawled(pages) if p.title and not (min_len <= len(p.title) <= max_len)
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_003", "Metadata", Severity.LOW,
        "Title length outside recommended range",
        f"Titles shorter than {min_len} or longer than {max_len} characters tend to get truncated or under-describe the page in search results.",
        f"Aim for a title between {min_len} and {max_len} characters.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_meta_description(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.indexable and not p.meta_description]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_004", "Metadata", Severity.MEDIUM,
        "Missing meta description",
        "These pages have no meta description, so search engines generate their own snippet — often less compelling.",
        "Write a concise, unique meta description summarizing each page.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def duplicate_meta_description(pages, links, cfg) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in _crawled(pages):
        if p.indexable and p.meta_description:
            groups[p.meta_description.strip().lower()].append(p)
    affected = [(p.id, {"url": p.url}) for pages_ in groups.values() if len(pages_) > 1 for p in pages_]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_005", "Metadata", Severity.MEDIUM,
        "Duplicate meta descriptions",
        "Multiple pages share the same meta description, weakening their individual search snippets.",
        "Give each page its own meta description.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def description_length(pages, links, cfg) -> RuleFinding | None:
    min_len = cfg.get("MIN_DESCRIPTION_LENGTH", DEFAULT_THRESHOLDS["MIN_DESCRIPTION_LENGTH"])
    max_len = cfg.get("MAX_DESCRIPTION_LENGTH", DEFAULT_THRESHOLDS["MAX_DESCRIPTION_LENGTH"])
    affected = [
        (p.id, {"url": p.url, "length": len(p.meta_description)})
        for p in _crawled(pages)
        if p.meta_description and not (min_len <= len(p.meta_description) <= max_len)
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_006", "Metadata", Severity.LOW,
        "Meta description length outside recommended range",
        f"Descriptions shorter than {min_len} or longer than {max_len} characters are often truncated or under-informative in search results.",
        f"Aim for a meta description between {min_len} and {max_len} characters.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_h1(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.indexable and p.h1_count == 0]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_007", "Metadata", Severity.MEDIUM,
        "Missing H1 heading",
        "These pages have no H1, losing a strong on-page signal of what the page is about.",
        "Add exactly one descriptive H1 heading to each page.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def multiple_h1(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url, "h1_count": p.h1_count}) for p in _crawled(pages) if p.h1_count > 1]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_008", "Metadata", Severity.LOW,
        "Multiple H1 headings",
        "These pages use more than one H1, diluting the page's primary topic signal.",
        "Keep a single H1 per page and demote the rest to H2/H3.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


# ── Content ──────────────────────────────────────────────────────────
@rule
def thin_content(pages, links, cfg) -> RuleFinding | None:
    threshold = cfg.get("THIN_CONTENT_WORD_THRESHOLD", DEFAULT_THRESHOLDS["THIN_CONTENT_WORD_THRESHOLD"])
    affected = [
        (p.id, {"url": p.url, "word_count": p.word_count})
        for p in _crawled(pages)
        if p.indexable and p.word_count is not None and 0 < p.word_count < threshold
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_001", "Content", Severity.MEDIUM,
        "Thin content",
        f"These pages have fewer than {threshold} words of visible text, which rarely satisfies search intent.",
        "Expand the content with genuinely useful information, or consolidate into a fuller page.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def empty_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.indexable and (p.word_count or 0) == 0]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_002", "Content", Severity.HIGH,
        "Empty pages",
        "These indexable pages have no visible text content at all.",
        "Add content, or remove/noindex the page if it serves no purpose.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def duplicate_content(pages, links, cfg) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in _crawled(pages):
        if p.content_hash and (p.word_count or 0) > 0:
            groups[p.content_hash].append(p)
    affected = [(p.id, {"url": p.url}) for pages_ in groups.values() if len(pages_) > 1 for p in pages_]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_003", "Content", Severity.HIGH,
        "Duplicate content",
        "These pages have identical extracted text content, which can cause search engines to pick the wrong page to rank — or none at all.",
        "Differentiate the content, or canonicalize/redirect to a single version.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def excessive_crawl_depth(pages, links, cfg) -> RuleFinding | None:
    max_depth = cfg.get("MAX_CRAWL_DEPTH_WARNING", DEFAULT_THRESHOLDS["MAX_CRAWL_DEPTH_WARNING"])
    affected = [(p.id, {"url": p.url, "crawl_depth": p.crawl_depth}) for p in pages if p.crawl_depth > max_depth]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_004", "Content", Severity.LOW,
        "Pages buried too deep in the site structure",
        f"These pages are more than {max_depth} clicks from the homepage, which weakens their internal link equity and discoverability.",
        "Add links from higher-level pages to bring important content closer to the homepage.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


# ── Links ────────────────────────────────────────────────────────────
@rule
def broken_internal_links(pages, links, cfg) -> RuleFinding | None:
    by_page = defaultdict(list)
    for link in links:
        if link.is_internal and link.status_code and link.status_code >= 400 and link.source_page_id:
            by_page[link.source_page_id].append(link.target_url)
    page_by_id = {p.id: p for p in pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "broken_targets": targets})
        for pid, targets in by_page.items()
    ]
    if not affected:
        return None
    total_broken_links = sum(len(t["broken_targets"]) for _, t in affected)
    return RuleFinding(
        "SEO_LINK_001", "Links", Severity.HIGH,
        "Broken internal links",
        "Some internal links point at pages that return an error, wasting crawl budget and hurting user experience.",
        "Update or remove links to point at a working URL.",
        score_impact=-1 * total_broken_links, affected=affected,
    )


@rule
def orphan_pages(pages, links, cfg) -> RuleFinding | None:
    inbound: Counter = Counter()
    for link in links:
        if link.is_internal and link.target_page_id:
            inbound[link.target_page_id] += 1

    crawled = _crawled(pages)
    if not crawled:
        return None
    homepage = min(crawled, key=lambda p: p.crawl_depth)

    affected = [
        (p.id, {"url": p.url})
        for p in crawled
        if p.id != homepage.id and p.indexable and inbound.get(p.id, 0) == 0
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_002", "Links", Severity.MEDIUM,
        "Orphan pages",
        "These indexable pages have no internal links pointing to them from any other crawled page, making them hard for both users and search engines to discover.",
        "Add internal links from relevant pages (navigation, related content, sitemap) to these URLs.",
        score_impact=-1.5 * len(affected), affected=affected,
    )


@rule
def dead_end_pages(pages, links, cfg) -> RuleFinding | None:
    outbound: Counter = Counter()
    for link in links:
        if link.is_internal and link.source_page_id:
            outbound[link.source_page_id] += 1

    affected = [
        (p.id, {"url": p.url})
        for p in _crawled(pages)
        if p.indexable and outbound.get(p.id, 0) == 0
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_003", "Links", Severity.LOW,
        "Dead-end pages",
        "These pages have no outbound internal links, offering visitors and crawlers nowhere else to go on the site.",
        "Add relevant internal links (related articles, navigation, calls to action) to keep users and crawlers moving.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


# ── Images ───────────────────────────────────────────────────────────
@rule
def images_missing_alt(pages, links, cfg) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "missing": p.images_missing_alt, "total": p.images_total})
        for p in _crawled(pages) if p.images_missing_alt > 0
    ]
    if not affected:
        return None
    total_missing = sum(a[1]["missing"] for a in affected)
    return RuleFinding(
        "SEO_IMG_001", "Images", Severity.MEDIUM,
        "Images missing alt text",
        "Images without alt text are invisible to screen readers and lose out on image-search relevance.",
        "Add a concise, descriptive alt attribute to every meaningful image.",
        score_impact=-0.5 * total_missing, affected=affected,
    )


# ── Structured Data ──────────────────────────────────────────────────
@rule
def invalid_structured_data(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.schema_invalid]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SCHEMA_001", "Structured Data", Severity.MEDIUM,
        "Invalid structured data",
        "These pages contain JSON-LD that fails to parse, so search engines can't read the structured data at all.",
        "Fix the JSON-LD syntax (validate with Google's Rich Results Test or Schema.org's validator).",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def no_structured_data(pages, links, cfg) -> RuleFinding | None:
    crawled = _crawled(pages)
    affected = [(p.id, {"url": p.url}) for p in crawled if p.indexable and not p.has_schema]
    # Only flag this site-wide if *no* page anywhere has schema — a single
    # missing block on one page of a well-structured site isn't worth a
    # separate line item.
    if not affected or any(p.has_schema for p in crawled):
        return None
    return RuleFinding(
        "SEO_SCHEMA_002", "Structured Data", Severity.INFO,
        "No structured data found",
        "No JSON-LD structured data was found anywhere on the site, missing an opportunity for rich results and better AI/answer-engine readability.",
        "Add Organization, WebSite, and content-type-appropriate (Article/Product/FAQ) schema.",
        score_impact=-1, affected=affected,
    )


# ── Security ─────────────────────────────────────────────────────────
@rule
def http_pages(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.url.lower().startswith("http://")]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_001", "Security", Severity.HIGH,
        "Pages served over HTTP",
        "These pages are served without TLS, which browsers flag as insecure and which Google treats as a ranking negative.",
        "Serve the entire site over HTTPS and redirect all HTTP requests.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def mixed_content(pages, links, cfg) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in _crawled(pages) if p.mixed_content]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_002", "Security", Severity.MEDIUM,
        "Mixed content",
        "These HTTPS pages load at least one resource over plain HTTP, which browsers may block or flag as insecure.",
        "Update all sub-resource URLs (images, scripts, stylesheets) to HTTPS.",
        score_impact=-1 * len(affected), affected=affected,
    )


def run_all_rules(
    pages: list[CrawlPage], links: list[PageLink], rule_config: dict | None = None
) -> list[RuleFinding]:
    cfg = {**DEFAULT_THRESHOLDS, **(rule_config or {})}
    findings = []
    for fn in _REGISTRY:
        result = fn(pages, links, cfg)
        if result is not None:
            findings.append(result)
    return findings
