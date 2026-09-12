"""§23 International rules (hreflang) — a category M1 explicitly left as a
known gap; built out for M2.
"""
from __future__ import annotations

import re

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

# BCP47-ish: a 2-3 letter language code, optionally a region subtag, or the
# special "x-default" value. Not a full BCP47 validator, but catches the
# overwhelming majority of real mistakes (typos, wrong separators).
_VALID_HREFLANG_RE = re.compile(r"^([a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?|x-default)$")


def _sites_use_hreflang(ctx: RuleContext) -> bool:
    return any(p.hreflang_tags for p in ctx.pages)


@rule
def hreflang_missing_self_reference(ctx: RuleContext) -> RuleFinding | None:
    if not _sites_use_hreflang(ctx):
        return None
    affected = []
    for p in ctx.crawled():
        if not p.hreflang_tags:
            continue
        urls = {t.get("url") for t in p.hreflang_tags}
        # A canonicalized duplicate is not "a page" as far as indexing is
        # concerned — Google consolidates it into its canonical and evaluates
        # that URL's own signals, not this one's. So an hreflang block that
        # references the canonical instead of the literal fetched URL is a
        # self-reference in every sense that matters, not a missing one.
        # Without this, a site whose homepage is reachable at both "/" and
        # "/index.html" (a relative nav link, not a mistake) gets flagged
        # for hreflang on the URL nobody was ever supposed to treat as
        # separate from "/" in the first place.
        if p.normalized_url not in urls and (not p.canonical_url or p.canonical_url not in urls):
            affected.append((p.id, {"url": p.url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INTL_001", "International", Severity.MEDIUM,
        "hreflang missing self-reference",
        "These pages declare hreflang alternates for other language/region versions but don't include a "
        "hreflang tag pointing at themselves — Google's documentation explicitly requires a self-referencing entry.",
        "Add a hreflang tag on each page that points to that page's own URL.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def hreflang_invalid_language_code(ctx: RuleContext) -> RuleFinding | None:
    if not _sites_use_hreflang(ctx):
        return None
    affected = []
    for p in ctx.crawled():
        bad_codes = [t["lang"] for t in p.hreflang_tags if not _VALID_HREFLANG_RE.match(t.get("lang", ""))]
        if bad_codes:
            affected.append((p.id, {"url": p.url, "invalid_codes": bad_codes}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INTL_002", "International", Severity.MEDIUM,
        "Invalid hreflang language code",
        "These pages use a hreflang value that doesn't look like a valid language code, so browsers/search "
        "engines will likely ignore that alternate entirely.",
        "Use a valid ISO 639-1 language code, optionally with an ISO 3166-1 region (e.g. \"en\", \"en-US\", \"x-default\").",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def hreflang_points_to_non_indexable(ctx: RuleContext) -> RuleFinding | None:
    if not _sites_use_hreflang(ctx):
        return None
    by_normalized = ctx.by_normalized_url()
    affected = []
    for p in ctx.crawled():
        bad_targets = []
        for tag in p.hreflang_tags:
            target = by_normalized.get(tag.get("url"))
            if target is not None and (
                (target.status_code and target.status_code >= 400) or not target.indexable
            ):
                bad_targets.append(tag["url"])
        if bad_targets:
            affected.append((p.id, {"url": p.url, "bad_targets": bad_targets}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INTL_003", "International", Severity.HIGH,
        "hreflang points to a broken or non-indexable page",
        "Some hreflang alternates point at pages that are broken or marked noindex, so search engines can't "
        "actually serve that language/region alternative.",
        "Point hreflang tags at working, indexable pages only.",
        score_impact=-1.5 * len(affected), affected=affected,
    )


@rule
def hreflang_return_tag_missing(ctx: RuleContext) -> RuleFinding | None:
    if not _sites_use_hreflang(ctx):
        return None
    by_normalized = ctx.by_normalized_url()
    affected = []
    for p in ctx.crawled():
        # What an alternate is expected to point back to: this page's own
        # URL, or its canonical if it has one — same reasoning as the
        # self-reference rule above. A canonicalized duplicate's alternates
        # reciprocate to the canonical, not to the duplicate's own URL, and
        # that is the correct, not the broken, shape.
        acceptable_returns = {p.normalized_url}
        if p.canonical_url:
            acceptable_returns.add(p.canonical_url)
        for tag in p.hreflang_tags:
            target = by_normalized.get(tag.get("url"))
            if target is None or target.id == p.id:
                continue
            target_urls = {t.get("url") for t in (target.hreflang_tags or [])}
            if not (acceptable_returns & target_urls):
                affected.append((p.id, {"url": p.url, "points_to": tag["url"]}))
                break
    if not affected:
        return None
    return RuleFinding(
        "SEO_INTL_004", "International", Severity.MEDIUM,
        "hreflang missing reciprocal (return) tag",
        "These pages point to an alternate-language version that doesn't point back — Google requires "
        "hreflang annotations to be reciprocal (confirmed) on both pages, or it may ignore them.",
        "Ensure every hreflang alternate also declares a hreflang tag pointing back to the linking page.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def conflicting_lang_declarations(ctx: RuleContext) -> RuleFinding | None:
    if not _sites_use_hreflang(ctx):
        return None
    affected = []
    for p in ctx.crawled():
        if not p.html_lang or not p.hreflang_tags:
            continue
        self_entries = [t for t in p.hreflang_tags if t.get("url") == p.normalized_url]
        for entry in self_entries:
            raw = (entry.get("lang") or "").strip().lower()
            # x-default is a fallback marker, not a language, and it
            # legitimately points at a page that also declares its own
            # language. It has to be skipped *before* the subtag split —
            # splitting first leaves "x", which never equals "x-default",
            # so the guard never fired and every page whose x-default
            # correctly self-references was reported as conflicting.
            if raw == "x-default":
                continue
            declared = raw.split("-")[0]
            actual = p.html_lang.split("-")[0].lower()
            if declared and actual and declared != actual:
                affected.append((p.id, {"url": p.url, "html_lang": p.html_lang, "hreflang_self": entry.get("lang")}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_INTL_005", "International", Severity.LOW,
        "HTML lang and hreflang self-entry disagree",
        "On these pages, the <html lang> attribute and the page's own hreflang self-reference declare "
        "different languages — a confusing, conflicting signal.",
        "Make the html lang attribute match the language declared in the page's own hreflang entry.",
        score_impact=-0.25 * len(affected), affected=affected,
    )
