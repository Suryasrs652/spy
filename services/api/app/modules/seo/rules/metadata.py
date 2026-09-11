"""§23 Metadata rules."""
from __future__ import annotations

import re
from collections import defaultdict

from app.core.text_width import display_width, is_shouting
from app.modules.crawler.models import CrawlPage
from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

_GENERIC_TITLES = {"untitled", "home", "new page", "document", "index", "untitled document"}
_PUNCTUATION_RUN_RE = re.compile(r"[!?]{2,}")


@rule
def missing_title(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.title]
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
def duplicate_titles(ctx: RuleContext) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in ctx.indexable():
        if p.title:
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
def title_length(ctx: RuleContext) -> RuleFinding | None:
    min_len, max_len = ctx.config["MIN_TITLE_LENGTH"], ctx.config["MAX_TITLE_LENGTH"]
    affected = [
        (p.id, {"url": p.url, "title": p.title, "length": display_width(p.title)})
        for p in ctx.crawled() if p.title and not (min_len <= display_width(p.title) <= max_len)
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
def missing_meta_description(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.meta_description]
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
def duplicate_meta_description(ctx: RuleContext) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in ctx.indexable():
        if p.meta_description:
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
def description_length(ctx: RuleContext) -> RuleFinding | None:
    min_len, max_len = ctx.config["MIN_DESCRIPTION_LENGTH"], ctx.config["MAX_DESCRIPTION_LENGTH"]
    affected = [
        (p.id, {"url": p.url, "length": display_width(p.meta_description)})
        for p in ctx.crawled()
        if p.meta_description and not (min_len <= display_width(p.meta_description) <= max_len)
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
def missing_h1(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if p.h1_count == 0]
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
def multiple_h1(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url, "h1_count": p.h1_count}) for p in ctx.crawled() if p.h1_count > 1]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_008", "Metadata", Severity.LOW,
        "Multiple H1 headings",
        "These pages use more than one H1, diluting the page's primary topic signal.",
        "Keep a single H1 per page and demote the rest to H2/H3.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def duplicate_h1_across_pages(ctx: RuleContext) -> RuleFinding | None:
    groups: dict[str, list[CrawlPage]] = defaultdict(list)
    for p in ctx.indexable():
        if p.h1:
            groups[p.h1.strip().lower()].append(p)
    affected = [(p.id, {"url": p.url, "h1": p.h1}) for pages_ in groups.values() if len(pages_) > 1 for p in pages_]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_009", "Metadata", Severity.LOW,
        "Duplicate H1 across pages",
        "Multiple different pages use the exact same H1 heading, weakening each page's distinct topical signal.",
        "Write a unique H1 for each page that reflects its specific content.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def generic_page_title(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "title": p.title})
        for p in ctx.indexable()
        if p.title and p.title.strip().lower() in _GENERIC_TITLES
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_010", "Metadata", Severity.MEDIUM,
        "Generic, non-descriptive title",
        "These pages use a placeholder-style title (e.g. \"Home\", \"Untitled\") that says nothing about the page's content.",
        "Replace the title with a specific, descriptive one for each page.",
        score_impact=-1.5 * len(affected), affected=affected,
    )


@rule
def title_all_caps(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "title": p.title})
        for p in ctx.indexable()
        if p.title and is_shouting(p.title)
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_019", "Metadata", Severity.LOW,
        "Title written in all caps",
        "These pages' titles are written entirely in capital letters, which reads as shouting to users and "
        "is sometimes treated as a spam signal.",
        "Use normal sentence or title case instead of all caps.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def excessive_title_punctuation(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "title": p.title})
        for p in ctx.indexable()
        if p.title and _PUNCTUATION_RUN_RE.search(p.title)
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_020", "Metadata", Severity.LOW,
        "Excessive punctuation in title",
        "These titles contain runs of repeated ! or ? characters, which reads as spammy and can trigger "
        "search engines to rewrite the title in results.",
        "Use plain, single punctuation marks in titles.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def meta_description_all_caps(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url})
        for p in ctx.indexable()
        if p.meta_description and is_shouting(p.meta_description)
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_022", "Metadata", Severity.LOW,
        "Meta description written in all caps",
        "These pages' meta descriptions are written entirely in capital letters, which reads as shouting "
        "and looks unpolished in search results.",
        "Use normal sentence case instead of all caps.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def meta_description_echoes_title(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url})
        for p in ctx.indexable()
        if p.title and p.meta_description and p.title.strip().lower() == p.meta_description.strip().lower()
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_021", "Metadata", Severity.LOW,
        "Meta description just repeats the title",
        "These pages' meta description is identical to the title, wasting the opportunity to give searchers "
        "additional context in the snippet.",
        "Write a meta description that adds information beyond what's already in the title.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_og_title(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_og_title]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_011", "Metadata", Severity.MEDIUM,
        "Missing Open Graph title",
        "These pages have no og:title tag, so links shared on social platforms show a generic or missing title.",
        "Add an <meta property=\"og:title\"> tag to each page.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_og_description(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_og_description]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_012", "Metadata", Severity.LOW,
        "Missing Open Graph description",
        "These pages have no og:description tag, weakening how the page looks when shared on social platforms.",
        "Add a <meta property=\"og:description\"> tag to each page.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_og_image(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_og_image]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_013", "Metadata", Severity.MEDIUM,
        "Missing Open Graph image",
        "These pages have no og:image tag, so shared links on social platforms show no preview image.",
        "Add a <meta property=\"og:image\"> tag pointing at a representative image for each page.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_twitter_card(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_twitter_card]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_014", "Metadata", Severity.LOW,
        "Missing Twitter Card tag",
        "These pages have no twitter:card meta tag, so links shared on X/Twitter don't get a rich preview.",
        "Add a <meta name=\"twitter:card\"> tag (e.g. \"summary_large_image\") to each page.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_viewport_meta(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_viewport_meta]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_015", "Metadata", Severity.HIGH,
        "Missing viewport meta tag",
        "These pages have no viewport meta tag, meaning they likely aren't optimized for mobile — a major "
        "ranking and usability factor given mobile-first indexing.",
        "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to each page.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def missing_charset_meta(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_charset_meta]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_016", "Metadata", Severity.MEDIUM,
        "Missing character encoding declaration",
        "These pages don't declare a character encoding, which can cause the browser to misrender special "
        "characters and delays page rendering while the browser guesses.",
        "Add <meta charset=\"utf-8\"> as early as possible in the <head>.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_favicon(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.has_favicon]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_017", "Metadata", Severity.LOW,
        "Missing favicon",
        "These pages declare no favicon link, so the site shows a generic icon in browser tabs and search results.",
        "Add a <link rel=\"icon\"> tag pointing at a favicon file.",
        score_impact=-0.1 * len(affected), affected=affected,
    )


@rule
def missing_html_lang(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.indexable() if not p.html_lang]
    if not affected:
        return None
    return RuleFinding(
        "SEO_META_018", "Metadata", Severity.MEDIUM,
        "Missing HTML lang attribute",
        "These pages don't declare a language on the <html> tag, which can affect how search engines and "
        "screen readers interpret the content's language.",
        "Add a lang attribute to the <html> tag (e.g. <html lang=\"en\">).",
        score_impact=-0.5 * len(affected), affected=affected,
    )
