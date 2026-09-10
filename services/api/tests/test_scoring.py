"""§21/§22 Spy Score — pure, reproducible from stored evidence.

The golden-fixture test is the reproducibility guarantee itself: the exact
same crawl evidence must always yield the exact same score under one
score_version, or §22/§132 (immutable, versioned scoring) is meaningless.
"""
from __future__ import annotations

import uuid

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.spy_score import compute_spy_score
from app.modules.seo.rules import run_all_rules


def _page(**kwargs) -> CrawlPage:
    url = kwargs.get("url", "https://example.com/")
    defaults = dict(
        id=uuid.uuid4(), audit_id=uuid.uuid4(), project_id=uuid.uuid4(),
        url=url, normalized_url=url,
        status_code=200, content_type="text/html", title="Example Page",
        meta_description="A perfectly fine description of this page for testing purposes here.",
        h1="Example Heading", h1_count=1, canonical_url=url, robots_meta=None,
        word_count=500, content_hash=uuid.uuid4().hex, html_hash=uuid.uuid4().hex,
        crawl_depth=0, indexable=True, robots_allowed=True, response_ms=200, html_size=10000,
        redirect_count=0, images_total=0, images_missing_alt=0,
        has_schema=True, schema_types=["Organization", "WebSite"], schema_invalid=False, mixed_content=False,
        # M2 fields — defaulted to a "clean" page's values. CrawlPage is a
        # SQLAlchemy model whose column `default=` only applies at INSERT
        # time, not on plain Python construction, so every field a rule
        # might read must be set explicitly here or it's None in tests.
        h2_count=2, h3_count=0, heading_order_valid=True,
        has_og_title=True, has_og_description=True, has_og_image=True, has_twitter_card=True,
        has_viewport_meta=True, has_charset_meta=True, has_favicon=True,
        html_lang="en", hreflang_tags=[],
        images_missing_dimensions=0, images_generic_alt=0,
        has_insecure_form_action=False, word_frequency_top_ratio=0.02,
        from_sitemap=True, x_robots_tag=None,
        security_headers={
            "strict-transport-security": "max-age=31536000", "x-content-type-options": "nosniff",
            "content-security-policy": "default-src 'self'", "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin", "permissions-policy": "geolocation=()",
        },
        schema_blocks=[{
            "@type": "Organization", "name": "Example Co", "url": "https://example.com",
            "logo": "https://example.com/logo.png", "sameAs": ["https://twitter.com/example"],
        }],
        is_redirect_loop=False,
        # Full §48/§49 AEO/GEO signals — defaulted to a "clean" page's values.
        question_heading_count=1, list_count=1, table_count=0, has_definition_list=False,
        has_author_byline=True,
    )
    defaults.update(kwargs)
    return CrawlPage(**defaults)


def _clean_site(n: int = 5) -> list[CrawlPage]:
    return [
        _page(
            url=f"https://example.com/page-{i}",
            normalized_url=f"https://example.com/page-{i}",
            canonical_url=f"https://example.com/page-{i}",
            title=f"Unique Page Title {i}",
            meta_description=f"A unique, sufficiently descriptive summary of page {i} for search snippets.",
            crawl_depth=0 if i == 0 else 1,
        )
        for i in range(n)
    ]


def _citation_links(pages: list[CrawlPage]) -> list[PageLink]:
    """One outbound external link per page — the §49 citation-readiness signal."""
    return [
        PageLink(
            id=uuid.uuid4(), audit_id=p.audit_id, source_page_id=p.id,
            target_url="https://external-source.example/article", is_internal=False,
        )
        for p in pages
    ]


def _broken_site(n: int = 5) -> list[CrawlPage]:
    # Mirrors what the real crawler actually produces for a 5xx page
    # (app/modules/crawler/engine.py sets indexable=False whenever
    # status_code >= 400) rather than an unrealistic "500 but still
    # indexable" combination.
    return [
        _page(
            url=f"https://example.com/page-{i}",
            normalized_url=f"https://example.com/page-{i}",
            title=None, meta_description=None, h1=None, h1_count=0, canonical_url=None,
            word_count=0, status_code=500, indexable=False, has_schema=False, schema_types=[],
        )
        for i in range(n)
    ]


def test_perfect_site_scores_high() -> None:
    pages = _clean_site()
    findings = run_all_rules(pages, [])
    score = compute_spy_score(pages=pages, findings=findings, urls_processed=len(pages), links=_citation_links(pages))
    assert score.spy_score >= 90, f"expected a clean, schema-complete site to score highly, got {score.spy_score}"
    assert score.authority_score is None, "authority has no M1 data source and must not be guessed"


def test_broken_site_scores_much_lower_than_clean_site() -> None:
    clean_pages = _clean_site()
    clean_findings = run_all_rules(clean_pages, [])
    clean_score = compute_spy_score(
        pages=clean_pages, findings=clean_findings, urls_processed=5, links=_citation_links(clean_pages)
    )

    broken_pages = _broken_site()
    broken_findings = run_all_rules(broken_pages, [])
    broken_score = compute_spy_score(pages=broken_pages, findings=broken_findings, urls_processed=5)

    assert broken_score.spy_score < clean_score.spy_score - 20, (
        f"expected a badly broken site ({broken_score.spy_score}) to score well below "
        f"a clean one ({clean_score.spy_score})"
    )


def test_score_is_reproducible_for_identical_evidence() -> None:
    pages = _clean_site()
    findings1 = run_all_rules(pages, [])
    findings2 = run_all_rules(pages, [])
    score1 = compute_spy_score(pages=pages, findings=findings1, urls_processed=len(pages), links=_citation_links(pages))
    score2 = compute_spy_score(pages=pages, findings=findings2, urls_processed=len(pages), links=_citation_links(pages))
    assert score1.spy_score == score2.spy_score
    assert score1.evidence == score2.evidence


def test_weights_are_renormalized_without_authority() -> None:
    pages = _clean_site()
    findings = run_all_rules(pages, [])
    score = compute_spy_score(pages=pages, findings=findings, urls_processed=len(pages))
    weights = score.evidence["weights_used"]
    assert "authority" not in weights
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_confidence_scales_with_crawl_coverage() -> None:
    pages = _clean_site(n=3)
    findings = run_all_rules(pages, [])
    low = compute_spy_score(pages=pages, findings=findings, urls_processed=2, target_sample_size=20)
    high = compute_spy_score(pages=pages, findings=findings, urls_processed=20, target_sample_size=20)
    assert low.confidence < high.confidence
    assert high.confidence == 100.0


def test_aeo_score_rewards_question_headings_structured_content_and_bylines() -> None:
    """§48 full AEO: question coverage, structured content and bylines are
    real signals extracted by the crawler (parser.py), not guessed — a page
    with none of them must score lower than one with all of them.
    """
    rich_pages = _clean_site()
    plain_pages = [
        _page(
            url=p.url, normalized_url=p.normalized_url, canonical_url=p.canonical_url,
            title=p.title, meta_description=p.meta_description, crawl_depth=p.crawl_depth,
            question_heading_count=0, list_count=0, table_count=0, has_definition_list=False,
            has_author_byline=False,
        )
        for p in rich_pages
    ]

    rich_score = compute_spy_score(pages=rich_pages, findings=run_all_rules(rich_pages, []), urls_processed=len(rich_pages))
    plain_score = compute_spy_score(pages=plain_pages, findings=run_all_rules(plain_pages, []), urls_processed=len(plain_pages))

    assert rich_score.aeo_score > plain_score.aeo_score
    assert rich_score.evidence["aeo"]["question_coverage_pct"] == 100.0
    assert plain_score.evidence["aeo"]["question_coverage_pct"] == 0.0
    assert rich_score.evidence["aeo"]["structured_content_pct"] == 100.0
    assert plain_score.evidence["aeo"]["structured_content_pct"] == 0.0
    assert rich_score.evidence["aeo"]["byline_coverage_pct"] == 100.0
    assert plain_score.evidence["aeo"]["byline_coverage_pct"] == 0.0


def test_geo_score_penalizes_inconsistent_organization_names() -> None:
    """§49 entity consistency: the same brand naming itself differently on
    different pages is a real inconsistency signal (mirrors the
    SEO_SCHEMA_007 rule's own check), not a manufactured penalty.
    """
    consistent_pages = _clean_site()
    inconsistent_pages = _clean_site()
    inconsistent_pages[-1].schema_blocks = [
        {"@type": "Organization", "name": "A Totally Different Name", "url": "https://example.com"}
    ]

    consistent_score = compute_spy_score(
        pages=consistent_pages, findings=run_all_rules(consistent_pages, []), urls_processed=len(consistent_pages)
    )
    inconsistent_score = compute_spy_score(
        pages=inconsistent_pages, findings=run_all_rules(inconsistent_pages, []), urls_processed=len(inconsistent_pages)
    )

    assert consistent_score.evidence["geo"]["entity_name_consistency_pct"] == 100.0
    assert inconsistent_score.evidence["geo"]["entity_name_consistency_pct"] == 0.0
    assert inconsistent_score.geo_score < consistent_score.geo_score


def test_geo_score_rewards_citation_readiness() -> None:
    """§49 citation readiness: pages that link out to external sources are a
    real, measurable signal once the caller supplies the crawl's page links —
    absent that evidence, the signal is 0, never guessed."""
    pages = _clean_site()
    findings = run_all_rules(pages, [])

    without_citations = compute_spy_score(pages=pages, findings=findings, urls_processed=len(pages))
    with_citations = compute_spy_score(
        pages=pages, findings=findings, urls_processed=len(pages), links=_citation_links(pages)
    )

    assert without_citations.evidence["geo"]["citation_readiness_pct"] == 0.0
    assert with_citations.evidence["geo"]["citation_readiness_pct"] == 100.0
    assert with_citations.geo_score > without_citations.geo_score


def test_geo_score_rewards_organization_field_completeness() -> None:
    """A bare `{"@type": "Organization"}` is a much weaker GEO entity signal
    than one with logo and sameAs social profiles filled in (§49)."""
    rich_pages = _clean_site()
    bare_pages = _clean_site()
    for p in bare_pages:
        p.schema_blocks = [{"@type": "Organization", "name": "Example Co", "url": "https://example.com"}]

    rich_score = compute_spy_score(pages=rich_pages, findings=run_all_rules(rich_pages, []), urls_processed=len(rich_pages))
    bare_score = compute_spy_score(pages=bare_pages, findings=run_all_rules(bare_pages, []), urls_processed=len(bare_pages))

    assert rich_score.evidence["geo"]["org_field_completeness_pct"] == 100.0
    assert bare_score.evidence["geo"]["org_field_completeness_pct"] == 50.0
    assert rich_score.geo_score > bare_score.geo_score
