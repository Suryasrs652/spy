"""§23 Links rules."""
from __future__ import annotations

from collections import Counter, defaultdict
from urllib.parse import urlsplit

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

_GENERIC_ANCHORS = {"click here", "read more", "here", "link", "this page", "learn more", "more"}


@rule
def broken_internal_links(ctx: RuleContext) -> RuleFinding | None:
    by_page = defaultdict(list)
    for link in ctx.links:
        if link.is_internal and link.status_code and link.status_code >= 400 and link.source_page_id:
            by_page[link.source_page_id].append(link.target_url)
    page_by_id = {p.id: p for p in ctx.pages}
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
def orphan_pages(ctx: RuleContext) -> RuleFinding | None:
    inbound = ctx.inbound_internal_link_counts()
    crawled = ctx.crawled()
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
def dead_end_pages(ctx: RuleContext) -> RuleFinding | None:
    outbound = ctx.outbound_internal_link_counts()
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if outbound.get(p.id, 0) == 0]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_003", "Links", Severity.LOW,
        "Dead-end pages",
        "These pages have no outbound internal links, offering visitors and crawlers nowhere else to go on the site.",
        "Add relevant internal links (related articles, navigation, calls to action) to keep users and crawlers moving.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def broken_external_links(ctx: RuleContext) -> RuleFinding | None:
    by_page = defaultdict(list)
    for link in ctx.links:
        if not link.is_internal and link.status_code and link.status_code >= 400 and link.source_page_id:
            by_page[link.source_page_id].append({"target": link.target_url, "status": link.status_code})
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "broken_targets": targets})
        for pid, targets in by_page.items()
    ]
    if not affected:
        return None
    total = sum(len(t["broken_targets"]) for _, t in affected)
    return RuleFinding(
        "SEO_LINK_004", "Links", Severity.MEDIUM,
        "Broken external links",
        "Some outbound links point at external pages that returned an error when checked — a poor experience "
        "for anyone who clicks them, and a weak trust signal.",
        "Update or remove links to external pages that no longer exist.",
        score_impact=-0.5 * total, affected=affected,
    )


@rule
def redirect_loops(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.pages if p.is_redirect_loop]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_005", "Links", Severity.CRITICAL,
        "Redirect loop detected",
        "These URLs redirect back to a page already seen earlier in the same redirect chain, so the request "
        "never resolves — a dead end for both users and search engines.",
        "Fix the redirect configuration so the chain terminates at a real page.",
        score_impact=-3 * len(affected), affected=affected,
    )


@rule
def excessive_outbound_external_links(ctx: RuleContext) -> RuleFinding | None:
    limit = ctx.config["MAX_EXTERNAL_LINKS"]
    external_counts: dict = defaultdict(int)
    for link in ctx.links:
        if not link.is_internal and link.source_page_id:
            external_counts[link.source_page_id] += 1
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "external_link_count": count})
        for pid, count in external_counts.items() if count > limit
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_006", "Links", Severity.LOW,
        "Excessive outbound external links",
        f"These pages link out to more than {limit} external domains/pages, which can dilute link equity and "
        "occasionally reads as a low-quality or link-farm page.",
        "Trim outbound links to only the most relevant, valuable ones.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def nofollow_internal_links(ctx: RuleContext) -> RuleFinding | None:
    by_page = defaultdict(int)
    for link in ctx.links:
        if link.is_internal and link.nofollow and link.source_page_id:
            by_page[link.source_page_id] += 1
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "nofollow_internal_count": count})
        for pid, count in by_page.items()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_007", "Links", Severity.MEDIUM,
        "Nofollow on internal links",
        "These pages mark some of their own internal links as nofollow, which usually blocks link equity from "
        "flowing to those pages unintentionally.",
        "Remove the nofollow attribute from internal links unless deliberately blocking crawl of that page.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def generic_anchor_text(ctx: RuleContext) -> RuleFinding | None:
    by_page = defaultdict(int)
    for link in ctx.links:
        if link.is_internal and link.source_page_id and link.anchor_text:
            if link.anchor_text.strip().lower() in _GENERIC_ANCHORS:
                by_page[link.source_page_id] += 1
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "generic_anchor_count": count})
        for pid, count in by_page.items()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_008", "Links", Severity.LOW,
        "Generic anchor text",
        "Some internal links use non-descriptive anchor text like \"click here\" or \"read more\", which "
        "gives search engines and screen-reader users no context about the destination page.",
        "Use descriptive anchor text that reflects the linked page's topic.",
        score_impact=-0.1 * len(affected), affected=affected,
    )


@rule
def mixed_www_internal_links(ctx: RuleContext) -> RuleFinding | None:
    hosts = Counter()
    for link in ctx.links:
        if link.is_internal:
            hosts[urlsplit(link.target_url).netloc] += 1
    bare_hosts = {h for h in hosts if h and not h.startswith("www.")}
    www_hosts = {h[4:] for h in hosts if h.startswith("www.")}
    if not (bare_hosts & www_hosts):
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_LINK_009", "Links", Severity.LOW,
        "Inconsistent www/non-www internal links",
        "Internal links inconsistently use both the www and non-www form of the domain, splitting link "
        "signals and risking duplicate-content treatment for the same pages.",
        "Pick one canonical host (www or non-www) and use it consistently in all internal links.",
        score_impact=-0.5, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def internal_link_through_redirect(ctx: RuleContext) -> RuleFinding | None:
    page_by_id = {p.id: p for p in ctx.pages}
    by_page = defaultdict(list)
    for link in ctx.links:
        if not link.is_internal or not link.source_page_id or not link.target_page_id:
            continue
        target = page_by_id.get(link.target_page_id)
        if target and target.redirect_count > 0:
            by_page[link.source_page_id].append(link.target_url)
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "redirecting_targets": targets})
        for pid, targets in by_page.items()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_011", "Links", Severity.LOW,
        "Internal links pointing through a redirect",
        "These internal links point at a URL that itself redirects elsewhere, adding an unnecessary hop that "
        "slows the request and dilutes link equity.",
        "Update the link to point directly at the final destination URL.",
        score_impact=-0.1 * sum(len(t["redirecting_targets"]) for _, t in affected), affected=affected,
    )


@rule
def excessive_internal_links_on_page(ctx: RuleContext) -> RuleFinding | None:
    limit = ctx.config["MAX_INTERNAL_LINKS"]
    outbound = ctx.outbound_internal_link_counts()
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "internal_link_count": count})
        for pid, count in outbound.items() if count > limit
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_012", "Links", Severity.LOW,
        "Excessive internal links on a page",
        f"These pages link internally to more than {limit} other URLs, which dilutes the link-equity each "
        "individual link passes and can overwhelm both users and crawlers.",
        "Trim navigation/footer links or restructure the page to link only to the most relevant URLs.",
        score_impact=-0.1 * len(affected), affected=affected,
    )


@rule
def low_average_internal_linking(ctx: RuleContext) -> RuleFinding | None:
    min_avg = ctx.config["MIN_AVG_INTERNAL_LINKS_PER_PAGE"]
    indexable = ctx.indexable()
    if len(indexable) < 5:
        return None
    outbound = ctx.outbound_internal_link_counts()
    total_links = sum(outbound.get(p.id, 0) for p in indexable)
    avg = total_links / len(indexable)
    if avg >= min_avg:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth)
    return RuleFinding(
        "SEO_LINK_013", "Links", Severity.MEDIUM,
        "Weak internal linking site-wide",
        f"Pages on this site link to an average of only {avg:.1f} other internal pages, well below a "
        "healthy baseline — weak internal linking makes it harder for both users and search engines to "
        "discover related content.",
        "Add more contextual internal links (related content, navigation, in-body links) across the site.",
        score_impact=-1.5, affected=[(homepage.id, {"url": homepage.url, "avg_internal_links": round(avg, 2)})],
    )


@rule
def high_nofollow_ratio_sitewide(ctx: RuleContext) -> RuleFinding | None:
    max_ratio = ctx.config["MAX_NOFOLLOW_INTERNAL_RATIO"]
    internal_links = [link for link in ctx.links if link.is_internal]
    if len(internal_links) < 10:
        return None
    nofollow_count = sum(1 for link in internal_links if link.nofollow)
    ratio = nofollow_count / len(internal_links)
    if ratio <= max_ratio:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_LINK_014", "Links", Severity.MEDIUM,
        "High proportion of nofollow internal links",
        f"{ratio:.0%} of all internal links on this site are nofollow, which blocks a large share of "
        "internal link equity from flowing between pages.",
        "Review whether nofollow is actually intended on this many internal links; remove it where not needed.",
        score_impact=-1, affected=[(homepage.id, {"url": homepage.url, "nofollow_ratio": round(ratio, 2)})],
    )


@rule
def anchor_text_over_optimization(ctx: RuleContext) -> RuleFinding | None:
    counts: dict = defaultdict(int)
    for link in ctx.links:
        if link.is_internal and link.anchor_text:
            text = link.anchor_text.strip().lower()
            if len(text) > 3 and text not in {"home", "next", "previous", "back"}:
                counts[text] += 1
    internal_link_total = sum(1 for link in ctx.links if link.is_internal)
    if internal_link_total < 20 or not counts:
        return None
    top_anchor, top_count = max(counts.items(), key=lambda kv: kv[1])
    ratio = top_count / internal_link_total
    if ratio < 0.3 or top_count < 10:
        return None
    homepage = min(ctx.crawled(), key=lambda p: p.crawl_depth, default=None)
    if homepage is None:
        return None
    return RuleFinding(
        "SEO_LINK_015", "Links", Severity.LOW,
        "Possible internal anchor-text over-optimization",
        f"The exact anchor text \"{top_anchor}\" is used on {ratio:.0%} of all internal links site-wide — "
        "heavy repetition of one exact-match phrase can look manipulative to search engines.",
        "Vary internal link anchor text naturally instead of repeating the same exact phrase.",
        score_impact=-0.5, affected=[(homepage.id, {"url": homepage.url, "anchor_text": top_anchor, "ratio": round(ratio, 2)})],
    )


@rule
def http_internal_links_on_https_site(ctx: RuleContext) -> RuleFinding | None:
    by_page = defaultdict(int)
    for link in ctx.links:
        if link.is_internal and link.target_url.lower().startswith("http://") and link.source_page_id:
            by_page[link.source_page_id] += 1
    page_by_id = {p.id: p for p in ctx.pages}
    affected = [
        (pid, {"url": page_by_id[pid].url if pid in page_by_id else None, "http_link_count": count})
        for pid, count in by_page.items()
        if page_by_id.get(pid) and page_by_id[pid].url.lower().startswith("https://")
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_LINK_010", "Links", Severity.MEDIUM,
        "HTTPS pages linking internally over HTTP",
        "These HTTPS pages link to internal URLs using plain http://, forcing an unnecessary redirect and "
        "diluting link equity.",
        "Update internal links to use https:// directly.",
        score_impact=-0.5 * len(affected), affected=affected,
    )
