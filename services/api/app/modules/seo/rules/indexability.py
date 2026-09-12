"""§23 Indexability rules."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule


@rule
def noindex_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "robots_meta": p.robots_meta})
        for p in ctx.crawled() if "noindex" in (p.robots_meta or "").lower()
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
def missing_canonical(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.canonical_url]
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
def broken_canonical_target(ctx: RuleContext) -> RuleFinding | None:
    by_normalized = ctx.by_normalized_url()
    affected = []
    for p in ctx.crawled():
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


@rule
def canonical_cross_domain(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        if not p.canonical_url:
            continue
        page_host = urlsplit(p.normalized_url).netloc
        canonical_host = urlsplit(p.canonical_url).netloc
        if canonical_host and canonical_host != page_host:
            affected.append((p.id, {"url": p.url, "canonical_url": p.canonical_url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_004", "Indexability", Severity.HIGH,
        "Canonical points to a different domain",
        "These pages' canonical tags point at an entirely different domain — usually a mistake that tells "
        "search engines this content actually belongs to someone else's site.",
        "Fix the canonical URL to point within this site, unless cross-domain canonicalization is genuinely intended.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def canonical_points_to_noindex(ctx: RuleContext) -> RuleFinding | None:
    by_normalized = ctx.by_normalized_url()
    affected = []
    for p in ctx.crawled():
        if not p.canonical_url:
            continue
        target = by_normalized.get(p.canonical_url)
        if target is not None and target.status_code and target.status_code < 400 and not target.indexable:
            affected.append((p.id, {"url": p.url, "canonical_url": p.canonical_url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_005", "Indexability", Severity.HIGH,
        "Canonical points to a noindex page",
        "These pages' canonical tags point at a page that is itself marked noindex — the canonical target "
        "will never be indexed, so neither page ends up in search results.",
        "Point the canonical at an indexable page, or remove noindex from the target.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def noindex_but_in_sitemap(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url})
        for p in ctx.crawled()
        if p.from_sitemap and "noindex" in (p.robots_meta or "").lower()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_006", "Indexability", Severity.MEDIUM,
        "Sitemap includes noindex pages",
        "These URLs are listed in the XML sitemap but marked noindex — a conflicting signal that wastes "
        "search engines' crawl attention on pages that will never be indexed.",
        "Remove noindex pages from the sitemap, or remove noindex if they should be indexed.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def x_robots_noindex(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "x_robots_tag": p.x_robots_tag})
        for p in ctx.crawled()
        if p.x_robots_tag and "noindex" in p.x_robots_tag.lower()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_007", "Indexability", Severity.INFO,
        "Pages blocked via X-Robots-Tag header",
        "These pages send a noindex directive via the HTTP X-Robots-Tag header rather than a meta tag — "
        "confirm this is deliberate (it's easy to overlook since it isn't visible in the page source).",
        "Review the server/CDN configuration if any of these pages should actually be indexable.",
        score_impact=0, affected=affected,
    )


@rule
def conflicting_canonical_and_noindex(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        if p.canonical_url and p.canonical_url == p.normalized_url and "noindex" in (p.robots_meta or "").lower():
            affected.append((p.id, {"url": p.url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_009", "Indexability", Severity.MEDIUM,
        "Self-canonical page marked noindex",
        "These pages declare themselves as their own canonical (the authoritative version) but are also "
        "marked noindex — a contradictory pair of signals to search engines.",
        "Remove noindex if the page should be indexed, or remove the self-canonical if it genuinely shouldn't be.",
        score_impact=-0.75 * len(affected), affected=affected,
    )


@rule
def conflicting_robots_meta_directives(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        meta = (p.robots_meta or "").lower()
        if not meta:
            continue
        contradicts = ("index" in meta and "noindex" in meta) or ("follow" in meta and "nofollow" in meta and "unfollow" not in meta)
        if contradicts:
            affected.append((p.id, {"url": p.url, "robots_meta": p.robots_meta}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_010", "Indexability", Severity.MEDIUM,
        "Contradictory robots meta directives",
        "These pages' robots meta tag contains contradictory directives (e.g. both index and noindex), "
        "which search engines resolve unpredictably.",
        "Remove the contradictory directive so the meta robots tag states one clear intent.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def meta_and_x_robots_conflict(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        if not p.x_robots_tag or not p.robots_meta:
            continue
        meta_noindex = "noindex" in p.robots_meta.lower()
        header_noindex = "noindex" in p.x_robots_tag.lower()
        if meta_noindex != header_noindex:
            affected.append((p.id, {"url": p.url, "robots_meta": p.robots_meta, "x_robots_tag": p.x_robots_tag}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_011", "Indexability", Severity.MEDIUM,
        "Meta robots and X-Robots-Tag header disagree",
        "These pages' meta robots tag and their X-Robots-Tag HTTP header give conflicting indexing "
        "instructions — an easy-to-miss inconsistency since one lives in the HTML and the other in headers.",
        "Make the meta tag and header agree on whether the page should be indexed.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def sitemap_canonical_mismatch(ctx: RuleContext) -> RuleFinding | None:
    if not ctx.sitemap_found:
        return None
    affected = [
        (p.id, {"url": p.url, "canonical_url": p.canonical_url})
        for p in ctx.crawled()
        if p.from_sitemap and p.canonical_url and p.canonical_url != p.normalized_url
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_012", "Indexability", Severity.MEDIUM,
        "Sitemap lists a non-canonical URL",
        "These URLs are listed in the XML sitemap, but the page itself declares a different canonical URL — "
        "the sitemap is advertising a URL that isn't the one meant to be indexed.",
        "List the canonical URL in the sitemap instead of the non-canonical variant.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def sitemap_url_blocked_by_robots(ctx: RuleContext) -> RuleFinding | None:
    if not ctx.sitemap_found:
        return None
    affected = [
        (p.id, {"url": p.url})
        for p in ctx.pages
        if p.from_sitemap and not p.robots_allowed
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_INDEX_013", "Indexability", Severity.MEDIUM,
        "Sitemap includes a robots.txt-blocked URL",
        "These URLs are listed in the XML sitemap but robots.txt disallows crawling them — a direct "
        "contradiction that wastes search engines' attention on a URL they're told not to fetch.",
        "Remove blocked URLs from the sitemap, or update robots.txt to allow them if they should be indexed.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def indexable_not_in_sitemap(ctx: RuleContext) -> RuleFinding | None:
    if not ctx.sitemap_found:
        return None
    indexable = ctx.indexable()
    affected = [(p.id, {"url": p.url}) for p in indexable if not p.from_sitemap]
    # Only worth flagging when a meaningful share of the site is missing —
    # a handful of pages is normal (new content, sitemap not yet refreshed).
    if not affected or len(affected) < max(3, len(indexable) * 0.3):
        return None
    # Only as complete as sitemap discovery was, and index expansion is
    # capped.
    return RuleFinding(
        "SEO_INDEX_008", "Indexability", Severity.MEDIUM,
        "Indexable pages missing from the sitemap",
        "A large share of this site's indexable pages weren't listed in the XML sitemap, making them harder "
        "for search engines to discover efficiently.",
        "Regenerate the sitemap to include all indexable pages.",
        score_impact=-1 * len(affected), confidence=0.8, affected=affected,
    )
