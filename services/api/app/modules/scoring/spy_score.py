"""The three scores Spy reports, and the one number that combines them.

    OVERALL DIGITAL SEARCH SCORE
      SEO   — can a search engine crawl, index and rank this?
      AEO   — can an answer engine lift an answer out of it?
      GEO   — can a generative system tell who wrote it and reuse it?

These answer genuinely different questions, so they are computed separately
and reported separately. AEO and GEO used to be two 10% slices inside a
single composite, which meant a site could be excellent at both and see the
number move by almost nothing — and a reader had no way to tell a ranking
problem from a citability problem.

SEO is itself seven components out of 100 (see SEO_COMPONENT_WEIGHTS), AEO is
seven sub-scores and GEO is ten. Every one of them is a pure function of
stored crawl evidence and rule findings — no re-fetching, no LLM guessing
(§3). Every audit stores the `score_version` it was computed under; changing
a weight or a formula ships a new version string and never mutates a
completed audit's score (§22, §132).

Three things here are deliberately *not* scored, because the evidence to
score them does not exist in a crawl:

  - **Authority** is reported as unmeasured, not zero, whenever Spy's own
    crawl-derived backlink index has no referring domains for the site. That
    could mean "no backlinks" or "nobody Spy has crawled happens to link
    here", and a confident low score must never stand in for either.
  - **Original information gain** (GEO) needs a corpus to compare against.
  - **Off-site topical authority** needs the same. The on-site half — does
    this site actually cover its subject in depth — is measurable, and that
    is the only half `topical_authority` claims to measure.

Where a component has no evidence, its weight is redistributed across the
components that do, rather than being scored as a failure.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from app.core.schema_org import ORGANIZATION_TYPES
from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.acrs import (
    evidence_from_components,
    measure_citation_signals,
    score_from_components,
)
from app.modules.seo.rules import RuleFinding

CURRENT_SCORE_VERSION = "spy-score-v2.0"

# The headline number. SEO carries the most weight because it still decides
# whether anyone arrives at all; AEO and GEO decide what happens to the
# content once a machine has it, and are weighted equally to each other
# because neither is subordinate to the other.
SEARCH_SCORE_WEIGHTS = {"seo": 0.60, "aeo": 0.20, "geo": 0.20}

# SEO out of 100, as seven components.
SEO_COMPONENT_WEIGHTS = {
    "technical": 0.25,
    "onpage": 0.20,
    "content": 0.20,
    "internal_links": 0.10,
    "structured_data": 0.10,
    "performance": 0.10,
    "authority": 0.05,
}

AEO_COMPONENT_WEIGHTS = {
    "answerability": 0.20,
    "question_coverage": 0.15,
    "passage_extraction": 0.15,
    "structured_answers": 0.15,
    "schema_support": 0.15,
    "faq_implementation": 0.10,
    "entity_clarity": 0.10,
}

GEO_COMPONENT_WEIGHTS = {
    "entity_recognition": 0.15,
    "citation_readiness": 0.12,
    "fact_density": 0.12,
    "brand_consistency": 0.10,
    "source_attribution": 0.10,
    "knowledge_graph_signals": 0.10,
    "topical_authority": 0.10,
    "author_transparency": 0.08,
    "ai_readable_structure": 0.08,
    # Listed with a weight so it is on the record as a dimension that
    # belongs here, and always dropped, because establishing that
    # information appears nowhere else requires a corpus to compare
    # against. Its weight is redistributed across the nine that are real.
    "original_information_gain": 0.05,
}

_SEVERITY_DEDUCTION = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3, "INFO": 0}

_TECHNICAL_CATEGORIES = {"Crawlability", "Indexability", "Security", "International"}
_ONPAGE_CATEGORIES = {"Metadata", "Images"}
_CONTENT_CATEGORIES = {"Content"}
_INTERNAL_LINK_CATEGORIES = {"Links"}
_STRUCTURED_DATA_CATEGORIES = {"Structured Data"}

# Schema types that mark a page up as an explicit question-and-answer unit.
_FAQ_SCHEMA_TYPES = frozenset({"FAQPage", "QAPage", "HowTo"})

# Entity types that make the subject of a page unambiguous to a machine.
_ENTITY_SCHEMA_TYPES = frozenset({"Person", "Product", "Service"})

# The fields that make an entity resolvable in a knowledge graph rather than
# merely declared: who it is, where it lives, and what corroborates it.
_KNOWLEDGE_GRAPH_FIELDS = ("@id", "sameAs", "url", "logo")
_ORG_RICH_FIELDS = ("name", "url", "logo", "sameAs")

# A page has to say something substantial before it counts toward covering a
# subject in depth. Matches LONG_CONTENT_WORD_THRESHOLD in the rule engine.
SUBSTANTIVE_PAGE_WORDS = 600

# Roughly where on-site topical depth stops being the binding constraint: a
# site with thirty substantive pages on its subject is no longer thin, and
# the next thirty say much less than the first thirty did. Log-scaled for
# that reason, like the referring-domain curve below.
TOPICAL_BREADTH_TARGET = 30


@dataclass
class ScoreBreakdown:
    """`spy_score` is the Overall Digital Search Score; `seo_score` is the
    seven-component SEO score, and the four sub-component fields below it are
    parts of that, not peers of it.
    """

    spy_score: float
    seo_score: float
    aeo_score: float | None
    geo_score: float | None
    acrs_score: float
    # SEO sub-components, each out of 100.
    technical_score: float
    onpage_score: float
    content_score: float
    internal_links_score: float
    structured_data_score: float
    performance_score: float
    authority_score: float | None
    confidence: float
    score_version: str = CURRENT_SCORE_VERSION
    evidence: dict = field(default_factory=dict)


def _weighted(components: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Combine components under their weights, dropping any with no evidence
    and rescaling the rest to sum to 1.0.

    A component that could not be measured must not be scored as a zero —
    that turns "we didn't look" into "you failed", which is the one error
    this engine exists to avoid. Returns None when nothing was measurable.
    """
    present = {k: (v, weights[k]) for k, v in components.items() if v is not None}
    total_weight = sum(w for _v, w in present.values())
    if not total_weight:
        return None
    return sum(v * (w / total_weight) for v, w in present.values())


def _weights_used(components: dict[str, float | None], weights: dict[str, float]) -> dict[str, float]:
    present = {k: weights[k] for k, v in components.items() if v is not None}
    total = sum(present.values())
    return {k: round(w / total, 4) for k, w in present.items()} if total else {}


def _rounded(components: dict[str, float | None]) -> dict[str, float | None]:
    return {k: (round(v, 1) if v is not None else None) for k, v in components.items()}


def _category_score(findings: list[RuleFinding], categories: set[str], total_pages: int) -> float:
    """100 minus a deduction per finding, scaled by how much of the site it
    affects and how severe it is."""
    if total_pages == 0:
        return 0.0
    deduction = 0.0
    for f in findings:
        if f.category not in categories:
            continue
        weight = _SEVERITY_DEDUCTION.get(f.severity.value, 0)
        deduction += weight * (f.affected_count / total_pages)
    return round(max(0.0, 100.0 - deduction), 2)


def _performance_score(pages: list[CrawlPage]) -> float:
    timed = [p.response_ms for p in pages if p.response_ms is not None]
    if not timed:
        return 50.0  # no timing evidence collected — neutral, not a guess at "good"
    avg_ms = sum(timed) / len(timed)
    if avg_ms <= 500:
        return 100.0
    if avg_ms >= 5000:
        return 0.0
    return round(100.0 - ((avg_ms - 500) / (5000 - 500)) * 100.0, 2)


def _pct(matching: int, total: int) -> float:
    return 100.0 * matching / total if total else 0.0


def _schema_blocks_of_type(pages: list[CrawlPage], type_name: str | frozenset[str]):
    """Yields (page, block) for every stored JSON-LD block declaring
    `type_name`, mirroring the @type-as-str-or-list handling the structured-
    data rules already use (app/modules/seo/rules/structured_data.py).

    `type_name` may be a set, so a family of equivalent types (see
    ORGANIZATION_TYPES) can be matched in one pass.
    """
    wanted = {type_name} if isinstance(type_name, str) else type_name
    for p in pages:
        for block in p.schema_blocks or []:
            block_type = block.get("@type")
            types = block_type if isinstance(block_type, list) else [block_type]
            if wanted.intersection(types):
                yield p, block


# --------------------------------------------------------------------------
# AEO — can an answer engine lift an answer out of this site?
# --------------------------------------------------------------------------


def _nothing_to_score(
    pages: list[CrawlPage], citation_signals: dict[str, float] | None
) -> tuple[float | None, dict] | None:
    """The two ways a score can have no pages under it, which are not the
    same thing. Returns None when there *is* something to score.

    A site whose every page 500s or is marked noindex has been measured, and
    the measurement is zero: there is nothing for an answer engine to read.
    Redistributing that away as "unmeasurable" is how a totally broken site
    ends up outscoring a working one — it drops exactly the components that
    noticed the site was broken.

    An audit with no crawled pages at all is the genuinely unmeasurable case,
    and returns None so the weight moves to the components that do have data.
    """
    if not [p for p in pages if p.status_code is not None]:
        return None, {"reason": "no pages were crawled"}
    if citation_signals is None or not [p for p in pages if p.indexable]:
        return 0.0, {"reason": "no indexable pages — nothing on this site can be read or cited"}
    return None


def _aeo_score(pages: list[CrawlPage], citation_signals: dict[str, float] | None) -> tuple[float | None, dict]:
    empty = _nothing_to_score(pages, citation_signals)
    if empty is not None:
        return empty
    citation_signals = citation_signals or {}

    indexable = [p for p in pages if p.indexable]
    total = len(indexable)

    # Poses a question (or offers a definition/table) *and* has at least one
    # paragraph that survives being lifted away from its neighbours. Either
    # half alone is not an answer: a question with only context-dependent
    # prose under it cannot be quoted, and a liftable paragraph nobody asked
    # a question about will not be matched to a query.
    answerability = _pct(
        sum(
            1
            for p in indexable
            if ((p.question_heading_count or 0) > 0 or p.has_definition_list or (p.table_count or 0) > 0)
            and (p.self_contained_paragraph_count or 0) > 0
        ),
        total,
    )

    question_coverage = _pct(sum(1 for p in indexable if (p.question_heading_count or 0) > 0), total)
    structured_answers = _pct(
        sum(1 for p in indexable if p.list_count > 0 or p.table_count > 0 or p.has_definition_list),
        total,
    )
    schema_support = _pct(sum(1 for p in indexable if p.has_schema), total)

    # Of the pages that actually pose questions, how many mark them up so a
    # machine knows they are questions? Sites that answer nothing in question
    # form have no FAQ markup to be missing, so this is unmeasurable there
    # rather than a failure — a product catalogue is not worse for having no
    # FAQPage schema.
    question_pages = [p for p in indexable if (p.question_heading_count or 0) > 0]
    faq_implementation = (
        _pct(
            sum(1 for p in question_pages if _FAQ_SCHEMA_TYPES.intersection(p.schema_types or [])),
            len(question_pages),
        )
        if question_pages
        else None
    )

    components: dict[str, float | None] = {
        "answerability": answerability,
        "question_coverage": question_coverage,
        # Measured once in the ACRS engine and reused, so the two cannot
        # report different numbers for the same signal.
        "passage_extraction": citation_signals["passage_extractability"],
        "structured_answers": structured_answers,
        "schema_support": schema_support,
        "faq_implementation": faq_implementation,
        "entity_clarity": citation_signals["entity_clarity"],
    }
    score = _weighted(components, AEO_COMPONENT_WEIGHTS)
    evidence = {
        "components": _rounded(components),
        "weights_used": _weights_used(components, AEO_COMPONENT_WEIGHTS),
        "pages_scored": total,
        "pages_posing_questions": len(question_pages),
    }
    if faq_implementation is None:
        evidence["not_measured"] = [
            "faq_implementation — no page on this site poses a question in a heading, "
            "so there is no Q&A content for FAQ markup to be missing from"
        ]
    return (round(score, 2) if score is not None else None), evidence


# --------------------------------------------------------------------------
# GEO — can a generative system tell who wrote this and reuse it?
# --------------------------------------------------------------------------


def _brand_consistency_pct(pages: list[CrawlPage]) -> float | None:
    """How much of the site agrees on what the organization is called.

    The share of named Organization blocks carrying the most common name —
    so one stray variant on a 40-page site reads as a 97% consistent brand,
    not a failed one, while a site genuinely split between two names lands
    near 50%.
    """
    names = Counter(
        block["name"]
        for _p, block in _schema_blocks_of_type(pages, ORGANIZATION_TYPES)
        if isinstance(block.get("name"), str) and block["name"].strip()
    )
    if not names:
        return None
    return 100.0 * names.most_common(1)[0][1] / sum(names.values())


def _knowledge_graph_pct(pages: list[CrawlPage]) -> float | None:
    """Of the fields that let a knowledge graph resolve this entity to a real
    one — an @id to key it on, sameAs profiles to corroborate it, a URL and a
    logo — how many are actually present?"""
    orgs = list(_schema_blocks_of_type(pages, ORGANIZATION_TYPES))
    if not orgs:
        return None
    present = sum(1 for _p, block in orgs for f in _KNOWLEDGE_GRAPH_FIELDS if block.get(f))
    return _pct(present, len(_KNOWLEDGE_GRAPH_FIELDS) * len(orgs))


def _org_field_completeness_pct(pages: list[CrawlPage]) -> float | None:
    orgs = list(_schema_blocks_of_type(pages, ORGANIZATION_TYPES))
    if not orgs:
        return None
    present = sum(1 for _p, block in orgs for f in _ORG_RICH_FIELDS if block.get(f))
    return _pct(present, len(_ORG_RICH_FIELDS) * len(orgs))


def _topical_authority_pct(indexable: list[CrawlPage]) -> float:
    """The on-site half of topical authority: does this site cover its
    subject in depth, and across enough pages to constitute coverage?

    Depth without breadth is a single good essay; breadth without depth is a
    sitemap of stubs. Neither is authority, so the two are multiplied rather
    than averaged. The off-site half — whether the rest of the web treats
    this site as an authority — needs a backlink corpus Spy does not have,
    and is not claimed here.
    """
    if not indexable:
        return 0.0
    substantive = [p for p in indexable if (p.word_count or 0) >= SUBSTANTIVE_PAGE_WORDS]
    depth = _pct(len(substantive), len(indexable))
    breadth = min(
        1.0, math.log10(len(substantive) + 1) / math.log10(TOPICAL_BREADTH_TARGET + 1)
    )
    return depth * breadth


def _geo_score(
    pages: list[CrawlPage], citation_signals: dict[str, float] | None
) -> tuple[float | None, dict]:
    empty = _nothing_to_score(pages, citation_signals)
    if empty is not None:
        return empty
    citation_signals = citation_signals or {}

    indexable = [p for p in pages if p.indexable]
    total = len(indexable)

    # Half for declaring an organization at all, half for how much of the
    # site carries any identifiable entity. A site with Organization schema
    # on the homepage alone is recognisable; one that identifies the subject
    # of every page is unambiguous.
    has_org_schema = any(ORGANIZATION_TYPES.intersection(p.schema_types or []) for p in pages)
    entity_page_pct = _pct(
        sum(
            1
            for p in indexable
            if (ORGANIZATION_TYPES | _ENTITY_SCHEMA_TYPES).intersection(p.schema_types or [])
        ),
        total,
    )
    entity_recognition = (50.0 if has_org_schema else 0.0) + 0.5 * entity_page_pct

    schema_coverage = _pct(sum(1 for p in indexable if p.has_schema), total)
    clean_headings = _pct(
        sum(1 for p in indexable if p.h1_count == 1 and p.heading_order_valid), total
    )
    structured_content = _pct(
        sum(1 for p in indexable if p.list_count > 0 or p.table_count > 0 or p.has_definition_list),
        total,
    )
    ai_readable_structure = (schema_coverage + clean_headings + structured_content) / 3

    components: dict[str, float | None] = {
        "entity_recognition": entity_recognition,
        # Can a passage be lifted out and quoted whole? That is what makes a
        # page citable, and it is measured once in the ACRS engine.
        "citation_readiness": citation_signals["passage_extractability"],
        "fact_density": citation_signals["fact_density"],
        "brand_consistency": _brand_consistency_pct(pages),
        "source_attribution": citation_signals["source_attribution"],
        "knowledge_graph_signals": _knowledge_graph_pct(pages),
        "topical_authority": _topical_authority_pct(indexable),
        "author_transparency": citation_signals["author_transparency"],
        "ai_readable_structure": ai_readable_structure,
        "original_information_gain": None,
    }
    score = _weighted(components, GEO_COMPONENT_WEIGHTS)

    not_measured = [
        "original_information_gain — requires a corpus to compare this site's "
        "content against; no amount of markup analysis establishes it",
    ]
    if components["brand_consistency"] is None:
        not_measured.append(
            "brand_consistency — no Organization schema declares a name to be consistent about"
        )
    if components["knowledge_graph_signals"] is None:
        not_measured.append(
            "knowledge_graph_signals — no Organization schema found to inspect"
        )

    evidence = {
        "components": _rounded(components),
        "weights_used": _weights_used(components, GEO_COMPONENT_WEIGHTS),
        "pages_scored": total,
        "has_organization_schema": has_org_schema,
        "org_field_completeness_pct": _rounded({"v": _org_field_completeness_pct(pages)})["v"],
        "topical_authority_caveat": (
            "on-site depth and breadth only; whether the wider web treats this site "
            "as an authority is not measured"
        ),
        "not_measured": not_measured,
    }
    return (round(score, 2) if score is not None else None), evidence


# --------------------------------------------------------------------------
# Authority — SEO's smallest component, and the one most often unmeasurable
# --------------------------------------------------------------------------


def _authority_score(
    pages: list[CrawlPage], *, referring_domains: int, total_backlinks: int
) -> tuple[float | None, dict]:
    """Built from internal PageRank (this audit's own crawl) and Spy's
    crawl-derived backlink index (app/modules/backlinks). That index only
    contains domains Spy has *already* crawled while auditing someone else's
    site, so a brand-new domain shows zero referring domains regardless of
    its real backlink profile. Reporting a low score there would manufacture
    a negative signal indistinguishable from "genuinely has no backlinks"
    (§3), so it returns None until there is at least one real referring
    domain to base a number on.
    """
    if referring_domains == 0:
        return None, {
            "referring_domains": 0, "total_backlinks": 0,
            "reason": "no backlinks discovered yet in Spy's own crawl index",
        }

    indexable = [p for p in pages if p.indexable]
    pageranks = [float(p.internal_pagerank) for p in indexable if p.internal_pagerank is not None]
    avg_pagerank = sum(pageranks) / len(pageranks) if pageranks else 0.0

    # Referring domains, log-scaled: 1->10 matters far more than 100->110,
    # and Spy's own index is nowhere near web-scale yet, so a modest cap
    # (50 referring domains -> 100) avoids implying more precision than
    # this evidence actually supports.
    referring_domains_score = min(100.0, 100 * math.log10(referring_domains + 1) / math.log10(51))

    score = 0.7 * referring_domains_score + 0.3 * avg_pagerank
    return round(score, 2), {
        "referring_domains": referring_domains,
        "total_backlinks": total_backlinks,
        "referring_domains_score": round(referring_domains_score, 1),
        "avg_internal_pagerank": round(avg_pagerank, 1),
        "coverage_caveat": "based on Spy's own crawl-discovered backlink index, not a comprehensive web-scale backlink database",
    }


# --------------------------------------------------------------------------


def compute_spy_score(
    *,
    pages: list[CrawlPage],
    findings: list[RuleFinding],
    urls_processed: int,
    links: list[PageLink] | None = None,
    target_sample_size: int = 20,
    referring_domains: int = 0,
    total_backlinks: int = 0,
) -> ScoreBreakdown:
    total_pages = len([p for p in pages if p.status_code is not None]) or 1

    technical = _category_score(findings, _TECHNICAL_CATEGORIES, total_pages)
    onpage = _category_score(findings, _ONPAGE_CATEGORIES, total_pages)
    content = _category_score(findings, _CONTENT_CATEGORIES, total_pages)
    internal_links = _category_score(findings, _INTERNAL_LINK_CATEGORIES, total_pages)
    structured_data = _category_score(findings, _STRUCTURED_DATA_CATEGORIES, total_pages)
    performance = _performance_score(pages)
    authority, authority_evidence = _authority_score(
        pages, referring_domains=referring_domains, total_backlinks=total_backlinks
    )

    seo_components: dict[str, float | None] = {
        "technical": technical,
        "onpage": onpage,
        "content": content,
        "internal_links": internal_links,
        "structured_data": structured_data,
        "performance": performance,
        "authority": authority,
    }
    seo = round(_weighted(seo_components, SEO_COMPONENT_WEIGHTS) or 0.0, 2)

    # Measured once and shared: ACRS, AEO and GEO all read from the same
    # citation signals, so "fact density" cannot mean two different things
    # in two different sections of the same report.
    citation_signals = measure_citation_signals(pages, links)
    acrs = round(score_from_components(citation_signals), 2) if citation_signals else 0.0
    aeo, aeo_evidence = _aeo_score(pages, citation_signals)
    geo, geo_evidence = _geo_score(pages, citation_signals)

    search_components: dict[str, float | None] = {"seo": seo, "aeo": aeo, "geo": geo}
    spy_score = round(_weighted(search_components, SEARCH_SCORE_WEIGHTS) or 0.0, 2)

    confidence = round(100 * min(1.0, urls_processed / target_sample_size), 2)

    return ScoreBreakdown(
        spy_score=spy_score,
        seo_score=seo,
        aeo_score=aeo,
        geo_score=geo,
        acrs_score=acrs,
        technical_score=technical,
        onpage_score=onpage,
        content_score=content,
        internal_links_score=internal_links,
        structured_data_score=structured_data,
        performance_score=performance,
        authority_score=authority,
        confidence=confidence,
        evidence={
            "search_weights_used": _weights_used(search_components, SEARCH_SCORE_WEIGHTS),
            "seo": {
                "components": _rounded(seo_components),
                "weights_used": _weights_used(seo_components, SEO_COMPONENT_WEIGHTS),
            },
            "authority": authority_evidence,
            "aeo": aeo_evidence,
            "geo": geo_evidence,
            "acrs": evidence_from_components(citation_signals, acrs),
            "total_pages_scored": total_pages,
            "urls_processed": urls_processed,
        },
    )
