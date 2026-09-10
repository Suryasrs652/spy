"""§23 Crawlability rules."""
from __future__ import annotations

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule


@rule
def broken_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "status_code": p.status_code})
        for p in ctx.crawled() if 400 <= p.status_code < 500
    ]
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
def server_error_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "status_code": p.status_code})
        for p in ctx.crawled() if p.status_code >= 500
    ]
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
def long_redirect_chains(ctx: RuleContext) -> RuleFinding | None:
    limit = ctx.config["MAX_REDIRECT_CHAIN_LENGTH"]
    affected = [
        (p.id, {"url": p.url, "redirect_count": p.redirect_count})
        for p in ctx.pages if p.redirect_count > limit
    ]
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
def robots_blocked_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.pages if not p.robots_allowed]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_004", "Crawlability", Severity.INFO,
        "Pages blocked by robots.txt",
        "These URLs were discovered but robots.txt disallows crawling them — confirm this is intentional.",
        "Review robots.txt if any of these pages should actually be indexable.",
        score_impact=0, affected=affected,
    )


@rule
def missing_robots_txt(ctx: RuleContext) -> RuleFinding | None:
    if ctx.robots_txt_found:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_CRAWL_005", "Crawlability", Severity.INFO,
        "No robots.txt found",
        "The site has no robots.txt file. This isn't required, but it's the standard place to declare "
        "sitemap location and crawl rules to search engines.",
        "Add a robots.txt file at the site root (even a minimal one allowing all crawling and listing your sitemap).",
        score_impact=-0.5, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def robots_txt_blocks_everything(ctx: RuleContext) -> RuleFinding | None:
    if not ctx.robots_disallow_all:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_CRAWL_006", "Crawlability", Severity.CRITICAL,
        "robots.txt blocks the entire site",
        "robots.txt disallows crawling of the whole site for this crawler's user-agent — if this applies to "
        "search engines too, the site cannot be indexed at all.",
        "Review robots.txt and remove the blanket Disallow rule unless the site is deliberately not meant to be indexed.",
        score_impact=-10, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def missing_sitemap(ctx: RuleContext) -> RuleFinding | None:
    if ctx.sitemap_found:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_CRAWL_007", "Crawlability", Severity.LOW,
        "No XML sitemap found",
        "No sitemap.xml was found (via robots.txt or the conventional /sitemap.xml path), making it harder "
        "for search engines to discover every page efficiently.",
        "Generate an XML sitemap and reference it from robots.txt.",
        score_impact=-1, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def slow_response_times(ctx: RuleContext) -> RuleFinding | None:
    threshold = ctx.config["SLOW_RESPONSE_MS"]
    affected = [
        (p.id, {"url": p.url, "response_ms": p.response_ms})
        for p in ctx.crawled() if p.response_ms and p.response_ms > threshold
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_008", "Crawlability", Severity.MEDIUM,
        "Slow server response times",
        f"These pages took more than {threshold}ms to respond, which both hurts user experience and can "
        "reduce how much of the site search engines crawl per visit.",
        "Investigate server/application performance for these URLs (caching, database queries, hosting tier).",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def large_html_pages(ctx: RuleContext) -> RuleFinding | None:
    threshold = ctx.config["LARGE_HTML_SIZE_BYTES"]
    affected = [
        (p.id, {"url": p.url, "html_size": p.html_size})
        for p in ctx.crawled() if p.html_size and p.html_size > threshold
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_009", "Crawlability", Severity.LOW,
        "Unusually large HTML pages",
        f"These pages' raw HTML exceeds {threshold // 1000}KB, which slows rendering and wastes crawl budget.",
        "Trim unnecessary markup, inline scripts/styles, or split the content across pages.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def duplicate_urls_trailing_slash(ctx: RuleContext) -> RuleFinding | None:
    by_url = ctx.by_normalized_url()
    affected = []
    seen_pairs: set[frozenset] = set()
    for url, page in by_url.items():
        if not page.indexable or (page.status_code or 0) >= 400:
            continue
        variant = url[:-1] if url.endswith("/") else url + "/"
        other = by_url.get(variant)
        if other is not None and other.indexable and (other.status_code or 0) < 400:
            pair = frozenset({page.id, other.id})
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                affected.append((page.id, {"url": page.url, "duplicate_variant": other.url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_CRAWL_011", "Crawlability", Severity.MEDIUM,
        "Both trailing-slash URL variants are live",
        "Both the with-slash and without-slash form of these URLs return a working, indexable page — two "
        "separate URLs search engines can index as duplicate content.",
        "301-redirect one variant to the other so only one canonical form is ever crawlable.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def crawl_budget_exhausted(ctx: RuleContext) -> RuleFinding | None:
    if not ctx.max_urls_reached:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_CRAWL_010", "Crawlability", Severity.INFO,
        "Site is larger than this audit's crawl limit",
        "The crawl reached its URL limit before running out of new pages to discover — this audit only "
        "reflects a subset of the site.",
        "Run a plan with a higher crawl-URL limit for full-site coverage.",
        score_impact=0, affected=[(homepage.id, {"url": homepage.url})],
    )
