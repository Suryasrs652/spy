"""§23 Content rules."""
from __future__ import annotations

import re
from collections import defaultdict

from app.modules.crawler.models import CrawlPage
from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

_PLACEHOLDER_RE = re.compile(r"\b(lorem ipsum|todo|tbd|coming soon|placeholder text|test page)\b", re.I)


@rule
def thin_content(ctx: RuleContext) -> RuleFinding | None:
    threshold = ctx.config["THIN_CONTENT_WORD_THRESHOLD"]
    affected = [
        (p.id, {"url": p.url, "word_count": p.word_count})
        for p in ctx.indexable()
        if p.word_count is not None and 0 < p.word_count < threshold
    ]
    if not affected:
        return None
    # A word count is exact; "thin" is the judgement. Contact, pricing and
    # legal pages are legitimately short.
    return RuleFinding(
        "SEO_CONTENT_001", "Content", Severity.MEDIUM,
        "Thin content",
        f"These pages have fewer than {threshold} words of visible text, which rarely satisfies search intent.",
        "Expand the content with genuinely useful information, or consolidate into a fuller page.",
        score_impact=-1 * len(affected), confidence=0.8, affected=affected,
    )


@rule
def empty_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if (p.word_count or 0) == 0]
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
def duplicate_content(ctx: RuleContext) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in ctx.crawled():
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
def excessive_crawl_depth(ctx: RuleContext) -> RuleFinding | None:
    max_depth = ctx.config["MAX_CRAWL_DEPTH_WARNING"]
    affected = [(p.id, {"url": p.url, "crawl_depth": p.crawl_depth}) for p in ctx.pages if p.crawl_depth > max_depth]
    if not affected:
        return None
    # Depth is measured from this crawl's entry point in BFS order, which
    # isn't always the shortest path a user would take.
    return RuleFinding(
        "SEO_CONTENT_004", "Content", Severity.LOW,
        "Pages buried too deep in the site structure",
        f"These pages are more than {max_depth} clicks from the homepage, which weakens their internal link equity and discoverability.",
        "Add links from higher-level pages to bring important content closer to the homepage.",
        score_impact=-0.5 * len(affected), confidence=0.7, affected=affected,
    )


@rule
def low_text_to_html_ratio(ctx: RuleContext) -> RuleFinding | None:
    min_ratio = ctx.config["MIN_TEXT_TO_HTML_RATIO"]
    affected = []
    for p in ctx.indexable():
        if not p.html_size or not p.word_count:
            continue
        # ~5.5 bytes/word is a reasonable average for English text — used to
        # estimate visible-text bytes without re-fetching the page.
        estimated_text_bytes = p.word_count * 5.5
        ratio = estimated_text_bytes / p.html_size
        if ratio < min_ratio:
            affected.append((p.id, {"url": p.url, "estimated_ratio": round(ratio, 3)}))
    if not affected:
        return None
    # A proxy for template bloat. An app shell produces the same ratio while
    # being exactly what it should be.
    return RuleFinding(
        "SEO_CONTENT_005", "Content", Severity.LOW,
        "Low text-to-HTML ratio",
        "These pages have very little visible text relative to their HTML size, often a sign of markup-heavy, "
        "content-light templates that search engines may treat as low-value.",
        "Reduce unnecessary markup/scripts, or add more substantive content.",
        score_impact=-0.5 * len(affected), confidence=0.6, affected=affected,
    )


@rule
def missing_subheadings_on_long_content(ctx: RuleContext) -> RuleFinding | None:
    threshold = ctx.config["LONG_CONTENT_WORD_THRESHOLD"]
    affected = [
        (p.id, {"url": p.url, "word_count": p.word_count})
        for p in ctx.indexable()
        if p.word_count and p.word_count > threshold and p.h2_count == 0 and p.h3_count == 0
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_006", "Content", Severity.LOW,
        "Long content with no subheadings",
        f"These pages have more than {threshold} words but no H2/H3 subheadings, making them harder to scan "
        "for both readers and search engines trying to understand structure.",
        "Break the content into sections with descriptive H2/H3 subheadings.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def broken_heading_hierarchy(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.heading_order_valid]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_007", "Content", Severity.MEDIUM,
        "Heading levels skip a level",
        "These pages jump from one heading level to a lower one without the levels in between (e.g. H2 "
        "straight to H4), breaking the document outline that search engines and screen readers rely on.",
        "Use heading levels in sequence — don't skip from H2 to H4 without an H3.",
        score_impact=-0.75 * len(affected), affected=affected,
    )


@rule
def placeholder_content_detected(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.indexable():
        haystack = " ".join(filter(None, [p.title, p.meta_description, p.h1]))
        if _PLACEHOLDER_RE.search(haystack):
            affected.append((p.id, {"url": p.url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_010", "Content", Severity.HIGH,
        "Placeholder text left in place",
        "These pages' title, description, or heading contain placeholder text (e.g. \"Lorem ipsum\", "
        "\"Coming soon\", \"TODO\") — a page that's live but not actually finished.",
        "Replace the placeholder text with real, finished content before the page is indexed.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def single_word_h1(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "h1": p.h1})
        for p in ctx.indexable()
        if p.h1 and len(p.h1.split()) == 1 and p.h1.lower() not in {"faq", "contact", "about"}
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_CONTENT_009", "Content", Severity.LOW,
        "Single-word H1",
        "These pages' H1 is a single generic word (e.g. \"Home\", \"Blog\"), giving search engines little "
        "signal about what the specific page covers.",
        "Write a more descriptive H1 that reflects the page's specific topic.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def possible_keyword_stuffing(ctx: RuleContext) -> RuleFinding | None:
    threshold = ctx.config["KEYWORD_STUFFING_RATIO"]
    affected = [
        (p.id, {"url": p.url, "top_word_ratio": float(p.word_frequency_top_ratio)})
        for p in ctx.indexable()
        if p.word_frequency_top_ratio and float(p.word_frequency_top_ratio) > threshold
    ]
    if not affected:
        return None
    # The weakest inference in the rule set: a page repeating its own product
    # name is indistinguishable from one stuffing a keyword.
    return RuleFinding(
        "SEO_CONTENT_008", "Content", Severity.MEDIUM,
        "Possible keyword stuffing",
        "On these pages, a single word makes up an unusually large share of all visible text — a common "
        "symptom of keyword stuffing, which search engines penalize.",
        "Rewrite the content naturally; vary phrasing instead of repeating the same word or phrase.",
        score_impact=-1 * len(affected), confidence=0.5, affected=affected,
    )
