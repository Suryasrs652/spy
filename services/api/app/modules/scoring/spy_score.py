"""§21/§22 Spy Score, plus the §48/§49 AEO/GEO reduced deterministic subset.

Pure function of stored crawl evidence + rule findings — no re-fetching, no
LLM guessing (§3). Every audit stores the `score_version` it was computed
under (`CURRENT_SCORE_VERSION`); a later change to weights or formulas ships
under a new version string and never mutates a completed audit's score
(§22, §132).

Authority (§144/M5) is built from internal PageRank plus Spy's own
crawl-derived backlink index (app/modules/backlinks) — real evidence, but
still reported as unavailable (weight redistributed to the components that
do have data, per §3's "never manufacture certainty" principle) whenever
that index has zero referring domains for this site, since that could mean
either "genuinely no backlinks" or just "nobody Spy has crawled yet happens
to link here" and the two must never look the same as a confident low
score. AEO (§48) and GEO (§49) are computed from the full deterministic
signal set the M2 crawler extracts — question-phrased headings, structured
content (lists/tables/definitions), author bylines, and full JSON-LD schema
blocks — rather than M1's reduced subset (schema presence + heading
hygiene only).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.schema_org import ORGANIZATION_TYPES
from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.acrs import compute_acrs
from app.modules.seo.rules import RuleFinding

CURRENT_SCORE_VERSION = "spy-score-v1.0"

# §21 composition. "authority" is included for documentation even though
# M1 has no data source for it; see _redistribute_weights.
COMPONENT_WEIGHTS = {
    "technical": 0.20,
    "onpage": 0.15,
    "content": 0.15,
    "performance": 0.10,
    "architecture": 0.10,
    "authority": 0.10,
    "aeo": 0.10,
    "geo": 0.10,
}

_SEVERITY_DEDUCTION = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3, "INFO": 0}

_TECHNICAL_CATEGORIES = {"Crawlability", "Indexability", "Security", "International"}
_ONPAGE_CATEGORIES = {"Metadata", "Images", "Structured Data"}
_CONTENT_CATEGORIES = {"Content"}
_ARCHITECTURE_CATEGORIES = {"Links"}


@dataclass
class ScoreBreakdown:
    spy_score: float
    technical_score: float
    seo_score: float
    content_score: float
    performance_score: float
    authority_score: float | None
    aeo_score: float
    geo_score: float
    acrs_score: float
    confidence: float
    score_version: str = CURRENT_SCORE_VERSION
    evidence: dict = field(default_factory=dict)


def _category_score(findings: list[RuleFinding], categories: set[str], total_pages: int) -> float:
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


_ORG_RICH_FIELDS = ("name", "url", "logo", "sameAs")



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


def _question_coverage_pct(indexable: list[CrawlPage]) -> float:
    return 100 * sum(1 for p in indexable if p.question_heading_count > 0) / len(indexable)


def _structured_content_pct(indexable: list[CrawlPage]) -> float:
    return 100 * sum(
        1 for p in indexable if p.list_count > 0 or p.table_count > 0 or p.has_definition_list
    ) / len(indexable)


def _byline_coverage_pct(indexable: list[CrawlPage]) -> float:
    return 100 * sum(1 for p in indexable if p.has_author_byline) / len(indexable)


def _aeo_score(pages: list[CrawlPage]) -> tuple[float, dict]:
    """§48 full AEO composition, all deterministic and re-derivable from
    stored crawl evidence:
      - schema coverage (machine-readable structure)
      - FAQPage schema presence (explicit Q&A structure)
      - question coverage (headings phrased as natural-language questions —
        a broader "does this page answer questions" signal than FAQ schema
        alone, since most sites answer questions in prose H2/H3s, not
        formal FAQ blocks)
      - structured-answer readability (lists/tables/definition lists, which
        answer engines and AI crawlers extract far more reliably than prose)
      - heading hygiene (exactly one H1, and no skipped ranks below it —
        answer engines use the H1 to find the page's primary topic and walk
        the outline beneath it to find the part that answers the question)
      - source attribution (author/byline markup — §48 "citation
        readability": AI systems favor content with clear authorship)
    """
    indexable = [p for p in pages if p.indexable]
    if not indexable:
        return 0.0, {"reason": "no indexable pages"}

    schema_coverage_pct = 100 * sum(1 for p in indexable if p.has_schema) / len(indexable)
    # Both halves matter and this used to count only the first: a page can
    # have exactly one H1 and still jump H1 -> H3, which breaks the outline
    # an answer engine walks. Counting only H1s reported 100% "clean" on a
    # site where 17% of pages skipped a rank, so the score credited hygiene
    # the site didn't have. `heading_order_valid` is already computed per
    # page by the parser and used by SEO_CONTENT_007; it just wasn't
    # reaching the score.
    clean_heading_pct = 100 * sum(
        1 for p in indexable if p.h1_count == 1 and p.heading_order_valid
    ) / len(indexable)
    question_coverage_pct = _question_coverage_pct(indexable)
    structured_content_pct = _structured_content_pct(indexable)
    byline_coverage_pct = _byline_coverage_pct(indexable)
    has_faq_schema = any("FAQPage" in (p.schema_types or []) for p in pages)

    score = (
        0.20 * schema_coverage_pct
        + 0.15 * clean_heading_pct
        + 0.15 * question_coverage_pct
        + 0.20 * structured_content_pct
        + 0.15 * byline_coverage_pct
        + 0.15 * (100 if has_faq_schema else 40)
    )
    return round(score, 2), {
        "schema_coverage_pct": round(schema_coverage_pct, 1),
        "clean_heading_pct": round(clean_heading_pct, 1),
        "question_coverage_pct": round(question_coverage_pct, 1),
        "structured_content_pct": round(structured_content_pct, 1),
        "byline_coverage_pct": round(byline_coverage_pct, 1),
        "has_faq_schema": has_faq_schema,
    }


def _org_field_completeness_pct(pages: list[CrawlPage]) -> float | None:
    orgs = list(_schema_blocks_of_type(pages, ORGANIZATION_TYPES))
    if not orgs:
        return None
    total_fields = len(_ORG_RICH_FIELDS) * len(orgs)
    present = sum(1 for _p, block in orgs for f in _ORG_RICH_FIELDS if block.get(f))
    return 100 * present / total_fields


def _entity_name_consistency_pct(pages: list[CrawlPage]) -> float | None:
    names = {block["name"] for _p, block in _schema_blocks_of_type(pages, ORGANIZATION_TYPES) if block.get("name")}
    if not names:
        return None
    return 100.0 if len(names) == 1 else 0.0


def _citation_readiness_pct(indexable: list[CrawlPage], links: list[PageLink] | None) -> float:
    if not links:
        return 0.0
    pages_with_outbound_citation = {link.source_page_id for link in links if not link.is_internal}
    return 100 * sum(1 for p in indexable if p.id in pages_with_outbound_citation) / len(indexable)


def _geo_score(pages: list[CrawlPage], links: list[PageLink] | None = None) -> tuple[float, dict]:
    """§49 full GEO composition, all deterministic and re-derivable from
    stored crawl evidence:
      - Organization-entity presence (is there a declared entity at all)
      - Organization field completeness (name/url/logo/sameAs — a bare
        `{"@type":"Organization"}` is a much weaker entity signal than one
        with a logo and verified social profiles via sameAs)
      - entity-name consistency across pages (a brand that names itself
        differently on different pages is an inconsistent entity signal
        that confuses AI systems about who they're citing — same check the
        SEO_SCHEMA_007 rule flags, reused here as a score input)
      - Person/Product/Service schema presence (a richer entity graph
        beyond just the organization itself)
      - machine-readable structure (overall schema coverage)
      - citation readiness (pages that link out to external sources, which
        AI answer engines weight as an evidence/citation signal, §49)

    Components with no evidence anywhere on the site (no Organization schema
    at all, so completeness/consistency are undefined rather than "zero")
    are dropped and the remaining weights rescaled — the same pattern
    `_redistribute_weights` uses for the top-level Spy Score, so an
    unmeasured signal is never silently scored as a failure.
    """
    indexable = [p for p in pages if p.indexable]
    if not indexable:
        return 0.0, {"reason": "no indexable pages"}

    has_org_schema = any(ORGANIZATION_TYPES.intersection(p.schema_types or []) for p in pages)
    schema_coverage_pct = 100 * sum(1 for p in indexable if p.has_schema) / len(indexable)
    org_completeness_pct = _org_field_completeness_pct(pages)
    entity_consistency_pct = _entity_name_consistency_pct(pages)
    has_entity_schema = any(
        t in (p.schema_types or []) for p in pages for t in ("Person", "Product", "Service")
    )
    citation_readiness_pct = _citation_readiness_pct(indexable, links)

    components: dict[str, tuple[float | None, float]] = {
        "org_presence": (100.0 if has_org_schema else 30.0, 0.20),
        "schema_coverage": (schema_coverage_pct, 0.15),
        "org_completeness": (org_completeness_pct, 0.20),
        "entity_consistency": (entity_consistency_pct, 0.15),
        "entity_schema": (100.0 if has_entity_schema else 40.0, 0.15),
        "citation_readiness": (citation_readiness_pct, 0.15),
    }
    present = {k: (v, w) for k, (v, w) in components.items() if v is not None}
    total_weight = sum(w for _v, w in present.values())
    score = sum(v * (w / total_weight) for v, w in present.values())

    return round(score, 2), {
        "has_organization_schema": has_org_schema,
        "schema_coverage_pct": round(schema_coverage_pct, 1),
        "org_field_completeness_pct": round(org_completeness_pct, 1) if org_completeness_pct is not None else None,
        "entity_name_consistency_pct": entity_consistency_pct,
        "has_person_or_product_schema": has_entity_schema,
        "citation_readiness_pct": round(citation_readiness_pct, 1),
    }


def _authority_score(pages: list[CrawlPage], *, referring_domains: int, total_backlinks: int) -> tuple[float | None, dict]:
    """§144/M5 — Spy Authority, built from real evidence Spy now has:
    internal PageRank distribution (this audit's own crawl) and Spy's own
    crawl-derived backlink index (app/modules/backlinks). That index only
    contains domains Spy has *already* crawled while auditing someone
    else's site — a brand-new domain, or one nobody happens to have linked
    to from an already-audited site yet, will show zero referring domains
    regardless of its real-world backlink profile. Reporting a low score
    in that case would manufacture a negative signal indistinguishable
    from "genuinely has no backlinks" (§3) — so this returns None (like
    the M1-M4 "no data source" case it replaces) until there is at least
    one real referring domain to base a number on.
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


def _redistribute_weights(available: dict[str, float | None]) -> dict[str, float]:
    """Drop components with no data (currently just `authority` in M1) and
    scale the remaining weights back up to sum to 1.0, rather than silently
    treating a missing component as a zero (which would unfairly tank the
    overall score for something the audit never measured).
    """
    present = {k: w for k, w in COMPONENT_WEIGHTS.items() if available.get(k) is not None}
    total = sum(present.values())
    return {k: w / total for k, w in present.items()}


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
    seo = _category_score(findings, _ONPAGE_CATEGORIES, total_pages)
    content = _category_score(findings, _CONTENT_CATEGORIES, total_pages)
    architecture = _category_score(findings, _ARCHITECTURE_CATEGORIES, total_pages)
    performance = _performance_score(pages)
    authority, authority_evidence = _authority_score(
        pages, referring_domains=referring_domains, total_backlinks=total_backlinks
    )
    aeo, aeo_evidence = _aeo_score(pages)
    geo, geo_evidence = _geo_score(pages, links)
    # ACRS is reported alongside the composite rather than inside it: it
    # asks a different question (would a generative system quote this?) and
    # folding it in would change what spy_score has always meant.
    acrs, acrs_evidence = compute_acrs(pages, links)

    # "architecture" (internal linking/orphans/depth, §21's "Internal
    # architecture" weight) contributes to the composite but has no
    # dedicated Audit column — the dashboard doesn't show it as its own
    # card (§20 only lists Spy/SEO/Technical/Content/Performance/Authority/
    # AEO/GEO) — so it lives in `evidence` for anyone who wants the detail.
    components = {
        "technical": technical, "onpage": seo, "content": content,
        "performance": performance, "architecture": architecture,
        "authority": authority, "aeo": aeo, "geo": geo,
    }
    weights = _redistribute_weights(components)
    spy_score = round(sum(components[k] * w for k, w in weights.items()), 2)

    confidence = round(100 * min(1.0, urls_processed / target_sample_size), 2)

    return ScoreBreakdown(
        spy_score=spy_score,
        technical_score=technical,
        seo_score=seo,
        content_score=content,
        performance_score=performance,
        authority_score=authority,
        aeo_score=aeo,
        geo_score=geo,
        acrs_score=acrs,
        confidence=confidence,
        evidence={
            "weights_used": weights,
            "architecture_score": architecture,
            "authority": authority_evidence,
            "aeo": aeo_evidence,
            "geo": geo_evidence,
            "acrs": acrs_evidence,
            "total_pages_scored": total_pages,
            "urls_processed": urls_processed,
        },
    )
