"""ACRS — AI Citation Readiness Score.

The question this answers is narrower than "is this page good": **if a
generative system wanted to quote this page as the answer to something,
could it, and would it be comfortable attributing the claim?**

That decomposes into things a crawler can actually observe. A passage gets
reused when it states something checkable, says when it was written, names
who wrote it and where the information came from, identifies the entity it
is about, answers a question rather than describing a company's ambitions,
and survives being lifted away from the paragraphs around it.

Every component below is computed from stored crawl evidence, on the same
terms as the rest of the scoring engine (§21/§22): deterministic, versioned,
and re-derivable from the audit's own rows. Two of the things worth knowing
about citation readiness are deliberately *not* scored, because no amount of
markup analysis can establish them:

  - whether a claim is true, and
  - whether the information appears nowhere else.

Both need a corpus and a judgement. Inventing a number for either would be
the exact failure this engine exists to avoid, so they are reported as
unmeasured rather than estimated.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.core.schema_org import ORGANIZATION_TYPES
from app.modules.crawler.models import CrawlPage, PageLink

# Entities that make the *subject* of a page unambiguous to a machine.
_ENTITY_TYPES = ORGANIZATION_TYPES | {"Person", "Product", "Service", "Article", "BlogPosting"}

# A page carrying at least this many checkable figures reads as evidence-
# backed rather than promotional. Two is a low bar on purpose: the intent is
# to separate "states facts" from "states none", not to reward stat-stuffing.
MIN_STATISTICS_FOR_CREDIT = 2

COMPONENT_WEIGHTS = {
    "fact_density": 0.20,
    "passage_extractability": 0.18,
    "source_attribution": 0.15,
    "author_transparency": 0.15,
    "answer_independence": 0.12,
    "entity_clarity": 0.12,
    "temporal_signals": 0.08,
}

ACRS_VERSION = "acrs-v1.0"


# An external target linked from more than this share of the site is
# chrome — a social profile, a platform badge, a partner logo in the footer.
BOILERPLATE_LINK_SHARE = 0.5

# Below this many pages there is no population to infer boilerplate from:
# on a three-page site a footer link and a cited source look identical, so
# the filter is skipped rather than guessing.
MIN_PAGES_FOR_BOILERPLATE_DETECTION = 5


def _pct(matching: int, total: int) -> float:
    return 100.0 * matching / total if total else 0.0


# A click-to-chat or booking-widget link is how a visitor reaches the
# business, not a source the page is citing — the same reason `mailto:`/
# `tel:` hrefs never become PageLink rows at all (app/modules/crawler/
# parser.py). These arrive as ordinary https:// links, though, and a contact
# page carrying one is nowhere near the boilerplate-frequency filter below
# (it appears on a handful of pages, not most of the site), so an explicit,
# domain-based exclusion is the only thing that catches it. Found on a real
# audit: a WhatsApp badge on four contact pages was the only "citation"
# behind a nonzero source_attribution score, on a site that otherwise
# cites nothing.
_CONTACT_MECHANISM_DOMAINS = frozenset({
    "wa.me", "api.whatsapp.com", "chat.whatsapp.com",
    "calendly.com", "cal.com", "m.me",
})


def _is_contact_mechanism(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    return host in _CONTACT_MECHANISM_DOMAINS


def _pages_citing_a_source(indexable: list[CrawlPage], links: list[PageLink] | None) -> set:
    """Page ids that link out to something other than sitewide chrome."""
    if not links:
        return set()

    page_ids = {p.id for p in indexable}
    external = [
        link for link in links
        if not link.is_internal
        and link.source_page_id in page_ids
        and not _is_contact_mechanism(link.target_url)
    ]

    if len(page_ids) < MIN_PAGES_FOR_BOILERPLATE_DETECTION:
        return {link.source_page_id for link in external}

    pages_per_target: dict[str, set] = {}
    for link in external:
        pages_per_target.setdefault(link.target_url, set()).add(link.source_page_id)

    boilerplate_cutoff = len(page_ids) * BOILERPLATE_LINK_SHARE
    return {
        link.source_page_id
        for link in external
        if len(pages_per_target[link.target_url]) <= boilerplate_cutoff
    }


def measure_citation_signals(
    pages: list[CrawlPage], links: list[PageLink] | None = None
) -> dict[str, float] | None:
    """The seven measured components, as percentages, unrounded.

    Split out from `compute_acrs` because the GEO score is built from several
    of these same signals (app/modules/scoring/spy_score.py). Measuring them
    in one place means GEO's "fact density" and ACRS's cannot drift into two
    different numbers under the same name.

    Returns None when there is no indexable page to measure.
    """
    indexable = [p for p in pages if p.indexable]
    if not indexable:
        return None

    total = len(indexable)

    # Does the page state anything a reader could verify?
    fact_density = _pct(
        sum(1 for p in indexable if (p.statistic_count or 0) >= MIN_STATISTICS_FOR_CREDIT), total
    )

    # Of the prose on the page, how much stands alone if lifted out? Averaged
    # per page rather than pooled, so one enormous page can't carry a site.
    ratios = [
        (p.self_contained_paragraph_count or 0) / p.paragraph_count
        for p in indexable
        if p.paragraph_count
    ]
    passage_extractability = 100.0 * sum(ratios) / len(ratios) if ratios else 0.0

    # Does the page point at where its information came from? An outbound
    # link to another domain is the only citation signal that survives a
    # crawl — mentions in prose are not machine-checkable.
    #
    # Boilerplate has to be excluded or this measures nothing: one social
    # profile in a shared footer appears on every page and would score a
    # site 100% for citing its own LinkedIn. A target linked from most of
    # the site is navigation, not a source.
    cited_page_ids = _pages_citing_a_source(indexable, links)
    source_attribution = _pct(sum(1 for p in indexable if p.id in cited_page_ids), total)

    author_transparency = _pct(sum(1 for p in indexable if p.has_author_byline), total)
    temporal_signals = _pct(sum(1 for p in indexable if p.has_publication_date), total)

    # A question the page poses and answers is the unit an answer engine
    # matches against; a definition or a table is the shape it lifts.
    answer_independence = _pct(
        sum(
            1
            for p in indexable
            if (p.question_heading_count or 0) > 0 or p.has_definition_list or (p.table_count or 0) > 0
        ),
        total,
    )

    entity_clarity = _pct(
        sum(1 for p in indexable if _ENTITY_TYPES.intersection(p.schema_types or [])), total
    )

    return {
        "fact_density": fact_density,
        "passage_extractability": passage_extractability,
        "source_attribution": source_attribution,
        "author_transparency": author_transparency,
        "answer_independence": answer_independence,
        "entity_clarity": entity_clarity,
        "temporal_signals": temporal_signals,
        "pages_scored": float(total),
    }


def score_from_components(components: dict[str, float]) -> float:
    return sum(components[name] * weight for name, weight in COMPONENT_WEIGHTS.items())


def evidence_from_components(components: dict[str, float] | None, score: float) -> dict:
    """The reported ACRS evidence block. Shared with the scoring engine, which
    measures the components once and feeds them to ACRS, AEO and GEO alike."""
    if components is None:
        return {"reason": "no indexable pages", "version": ACRS_VERSION}

    evidence = {
        name: round(value, 1) for name, value in components.items() if name != "pages_scored"
    }
    evidence.update(
        {
            "version": ACRS_VERSION,
            "weights_used": COMPONENT_WEIGHTS,
            "pages_scored": int(components["pages_scored"]),
            "citation_probability": citation_probability(score),
            # Named so a reader knows these were considered and excluded,
            # rather than overlooked.
            "not_measured": [
                "factual_accuracy — requires verifying claims against the world",
                "information_gain — requires a corpus to compare against",
            ],
        }
    )
    return evidence


def compute_acrs(pages: list[CrawlPage], links: list[PageLink] | None = None) -> tuple[float, dict]:
    """Returns (score, evidence) over the indexable pages of one audit."""
    components = measure_citation_signals(pages, links)
    if components is None:
        return 0.0, evidence_from_components(None, 0.0)
    score = score_from_components(components)
    return round(score, 2), evidence_from_components(components, score)


def citation_probability(score: float) -> str:
    """The banding the score is reported in. Deliberately coarse: the
    underlying signals justify a rough likelihood, not a percentage.
    """
    if score >= 75:
        return "VERY_HIGH"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"
