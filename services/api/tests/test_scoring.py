"""§21/§22 the three scores and the one that combines them — pure, and
reproducible from stored evidence.

The golden-fixture test is the reproducibility guarantee itself: the exact
same crawl evidence must always yield the exact same score under one
score_version, or §22/§132 (immutable, versioned scoring) is meaningless.

Note what `_clean_site` actually is: a site with clean *SEO*. It has titles,
descriptions, canonicals and schema, and that is all the SEO score asks for.
It is not thereby a citable site — it has no statistics, no dates, no FAQ
markup and nothing long enough to constitute depth — and the AEO and GEO
scores are supposed to say so. That separation is the point of the v2
restructure, so the tests below assert each score against what it measures
rather than expecting one number to be high everywhere.
"""
from __future__ import annotations

import uuid

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.spy_score import (
    AEO_COMPONENT_WEIGHTS,
    GEO_COMPONENT_WEIGHTS,
    SEARCH_SCORE_WEIGHTS,
    SEO_COMPONENT_WEIGHTS,
    compute_spy_score,
)
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
    """One outbound external link per page, each to a *different* source.

    Distinct targets matter: a single URL linked from most of the site is
    boilerplate, and the ACRS engine excludes it on purpose (one shared
    footer link would otherwise score a site 100% for citing its own
    LinkedIn). Real citations point somewhere page-specific.
    """
    return [
        PageLink(
            id=uuid.uuid4(), audit_id=p.audit_id, source_page_id=p.id,
            target_url=f"https://external-source.example/article-{i}", is_internal=False,
        )
        for i, p in enumerate(pages)
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


def _score(pages, **kwargs):
    links = kwargs.pop("links", None)
    return compute_spy_score(
        pages=pages, findings=run_all_rules(pages, links or []),
        urls_processed=len(pages), links=links, **kwargs,
    )


# --------------------------------------------------------------------------
# Composition — what each score is made of
# --------------------------------------------------------------------------


def test_every_weight_set_sums_to_one() -> None:
    for weights in (
        SEARCH_SCORE_WEIGHTS, SEO_COMPONENT_WEIGHTS, AEO_COMPONENT_WEIGHTS, GEO_COMPONENT_WEIGHTS
    ):
        assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_seo_has_seven_components_and_aeo_geo_are_not_among_them() -> None:
    """The restructure in one assertion. AEO and GEO used to be 10% slices of
    a single composite, so being excellent at either moved the headline
    number by almost nothing, and a reader could not tell a ranking problem
    from a citability problem."""
    assert len(SEO_COMPONENT_WEIGHTS) == 7
    assert "aeo" not in SEO_COMPONENT_WEIGHTS
    assert "geo" not in SEO_COMPONENT_WEIGHTS
    assert set(SEARCH_SCORE_WEIGHTS) == {"seo", "aeo", "geo"}


def test_overall_score_is_the_weighted_sum_of_the_three() -> None:
    pages = _clean_site()
    score = _score(pages, links=_citation_links(pages))
    expected = (
        SEARCH_SCORE_WEIGHTS["seo"] * score.seo_score
        + SEARCH_SCORE_WEIGHTS["aeo"] * score.aeo_score
        + SEARCH_SCORE_WEIGHTS["geo"] * score.geo_score
    )
    assert abs(score.spy_score - expected) < 0.01


def test_seo_is_the_weighted_sum_of_its_components() -> None:
    score = _score(_clean_site())
    components = score.evidence["seo"]["components"]
    weights = score.evidence["seo"]["weights_used"]
    expected = sum(components[k] * w for k, w in weights.items())
    assert abs(score.seo_score - expected) < 0.05


def test_clean_seo_site_scores_high_on_seo() -> None:
    pages = _clean_site()
    score = _score(pages, links=_citation_links(pages))
    assert score.seo_score >= 90, f"expected clean SEO evidence to score highly, got {score.seo_score}"
    assert score.authority_score is None, "authority has no data source here and must not be guessed"


def test_clean_seo_does_not_imply_a_citable_site() -> None:
    """A site can be technically immaculate and still give a generative
    system nothing to work with. If AEO and GEO simply tracked SEO they would
    not be worth computing separately."""
    pages = _clean_site()
    score = _score(pages, links=_citation_links(pages))
    assert score.seo_score > score.aeo_score
    assert score.seo_score > score.geo_score


def test_score_is_reproducible_for_identical_evidence() -> None:
    pages = _clean_site()
    links = _citation_links(pages)
    first = _score(pages, links=links)
    second = _score(pages, links=links)
    assert first.spy_score == second.spy_score
    assert first.evidence == second.evidence


def test_confidence_scales_with_crawl_coverage() -> None:
    pages = _clean_site(n=3)
    findings = run_all_rules(pages, [])
    low = compute_spy_score(pages=pages, findings=findings, urls_processed=2, target_sample_size=20)
    high = compute_spy_score(pages=pages, findings=findings, urls_processed=20, target_sample_size=20)
    assert low.confidence < high.confidence
    assert high.confidence == 100.0


# --------------------------------------------------------------------------
# A broken site must score badly, not become unmeasurable
# --------------------------------------------------------------------------


def test_broken_site_scores_much_lower_than_clean_site() -> None:
    clean = _clean_site()
    clean_score = _score(clean, links=_citation_links(clean))
    broken_score = _score(_broken_site())
    assert broken_score.spy_score < clean_score.spy_score - 20, (
        f"expected a badly broken site ({broken_score.spy_score}) to score well below "
        f"a clean one ({clean_score.spy_score})"
    )


def test_a_site_with_nothing_indexable_scores_zero_not_unmeasured() -> None:
    """Regression from the v2 restructure: treating "no indexable pages" as
    missing evidence redistributed AEO and GEO out of the overall score
    entirely, so a site where every page returned 500 outscored a working
    one — it dropped exactly the components that had noticed the site was
    broken. Nothing indexable is a measurement, and the measurement is zero.
    """
    score = _score(_broken_site())
    assert score.aeo_score == 0.0
    assert score.geo_score == 0.0
    assert "no indexable pages" in score.evidence["aeo"]["reason"]


def test_an_empty_crawl_is_unmeasurable_rather_than_zero() -> None:
    """The other direction: with nothing crawled there is no evidence either
    way, and inventing a zero would be indistinguishable from a real
    finding."""
    score = compute_spy_score(pages=[], findings=[], urls_processed=0)
    assert score.aeo_score is None
    assert score.geo_score is None
    assert "aeo" not in score.evidence["search_weights_used"]


# --------------------------------------------------------------------------
# AEO — can an answer engine lift an answer out of this site?
# --------------------------------------------------------------------------


def test_aeo_rewards_question_headings_and_structured_content() -> None:
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
    rich, plain = _score(rich_pages), _score(plain_pages)

    assert rich.aeo_score > plain.aeo_score
    assert rich.evidence["aeo"]["components"]["question_coverage"] == 100.0
    assert plain.evidence["aeo"]["components"]["question_coverage"] == 0.0
    assert rich.evidence["aeo"]["components"]["structured_answers"] == 100.0
    assert plain.evidence["aeo"]["components"]["structured_answers"] == 0.0


def test_answerability_needs_both_a_question_and_a_liftable_answer() -> None:
    """A question with only context-dependent prose under it cannot be
    quoted; a liftable paragraph nobody asked a question about will not be
    matched to a query. Either half alone is not an answer."""
    both = _clean_site(3)
    for p in both:
        p.paragraph_count, p.self_contained_paragraph_count = 4, 3

    question_only = _clean_site(3)
    for p in question_only:
        p.paragraph_count, p.self_contained_paragraph_count = 4, 0

    assert _score(both).evidence["aeo"]["components"]["answerability"] == 100.0
    assert _score(question_only).evidence["aeo"]["components"]["answerability"] == 0.0


def test_faq_implementation_is_unmeasured_when_no_page_asks_a_question() -> None:
    """A product catalogue is not worse for having no FAQPage schema. There
    is no Q&A content there for the markup to be missing from, so scoring it
    zero would invent a failure."""
    no_questions = _clean_site(3)
    for p in no_questions:
        p.question_heading_count = 0

    evidence = _score(no_questions).evidence["aeo"]
    assert evidence["components"]["faq_implementation"] is None
    assert "faq_implementation" not in evidence["weights_used"]
    assert any("faq_implementation" in reason for reason in evidence["not_measured"])


def test_faq_implementation_measures_markup_on_the_pages_that_ask_questions() -> None:
    marked_up = _clean_site(3)
    for p in marked_up:
        p.schema_types = ["Organization", "FAQPage"]

    assert _score(marked_up).evidence["aeo"]["components"]["faq_implementation"] == 100.0
    assert _score(_clean_site(3)).evidence["aeo"]["components"]["faq_implementation"] == 0.0


# --------------------------------------------------------------------------
# GEO — can a generative system tell who wrote this and reuse it?
# --------------------------------------------------------------------------


def test_brand_consistency_is_a_share_not_a_verdict() -> None:
    """One stray name variant on a five-page site is a 4-in-5 consistent
    brand, not a failed one. The old check returned 0 for any disagreement at
    all, which made a typo look identical to a site genuinely split between
    two names."""
    consistent = _clean_site()
    assert _score(consistent).evidence["geo"]["components"]["brand_consistency"] == 100.0

    one_variant = _clean_site()
    one_variant[-1].schema_blocks = [
        {"@type": "Organization", "name": "A Totally Different Name", "url": "https://example.com"}
    ]
    mixed = _score(one_variant)
    assert mixed.evidence["geo"]["components"]["brand_consistency"] == 80.0
    assert mixed.geo_score < _score(consistent).geo_score


def test_geo_rewards_pages_that_cite_outside_sources() -> None:
    pages = _clean_site()
    findings = run_all_rules(pages, [])
    without = compute_spy_score(pages=pages, findings=findings, urls_processed=len(pages))
    with_sources = compute_spy_score(
        pages=pages, findings=findings, urls_processed=len(pages), links=_citation_links(pages)
    )
    assert without.evidence["geo"]["components"]["source_attribution"] == 0.0
    assert with_sources.evidence["geo"]["components"]["source_attribution"] == 100.0
    assert with_sources.geo_score > without.geo_score


def test_knowledge_graph_signals_reward_a_resolvable_entity() -> None:
    """A bare Organization block declares an entity; one with an @id, a logo
    and sameAs profiles gives a knowledge graph something to resolve it
    against."""
    rich = _clean_site()
    bare = _clean_site()
    for p in bare:
        p.schema_blocks = [{"@type": "Organization", "name": "Example Co", "url": "https://example.com"}]

    rich_score, bare_score = _score(rich), _score(bare)
    assert rich_score.evidence["geo"]["components"]["knowledge_graph_signals"] == 75.0
    assert bare_score.evidence["geo"]["components"]["knowledge_graph_signals"] == 25.0
    assert rich_score.geo_score > bare_score.geo_score


def test_original_information_gain_is_always_reported_as_unmeasured() -> None:
    """It is a real GEO dimension and it is not derivable from a crawl —
    establishing that information appears nowhere else needs a corpus. It
    carries a weight so the omission is on the record, and is always dropped
    rather than estimated."""
    evidence = _score(_clean_site()).evidence["geo"]
    assert "original_information_gain" in GEO_COMPONENT_WEIGHTS
    assert evidence["components"]["original_information_gain"] is None
    assert "original_information_gain" not in evidence["weights_used"]
    assert any("original_information_gain" in reason for reason in evidence["not_measured"])


def test_topical_authority_needs_depth_and_breadth_together() -> None:
    """Depth without breadth is one good essay; breadth without depth is a
    sitemap of stubs. Neither is authority."""
    deep_and_broad = _clean_site(40)
    for p in deep_and_broad:
        p.word_count = 1200

    deep_but_narrow = _clean_site(2)
    for p in deep_but_narrow:
        p.word_count = 1200

    broad_but_thin = _clean_site(40)
    for p in broad_but_thin:
        p.word_count = 120

    def topical(pages):
        return _score(pages).evidence["geo"]["components"]["topical_authority"]

    assert topical(deep_and_broad) > topical(deep_but_narrow)
    assert topical(deep_and_broad) > topical(broad_but_thin)
    assert topical(broad_but_thin) == 0.0


def test_skipped_heading_ranks_lower_ai_readable_structure() -> None:
    """Regression: this counted only `h1_count == 1`, so a site whose pages
    jump H1 -> H3 reported clean headings and the score credited hygiene it
    didn't have. A broken outline is exactly what stops a machine finding the
    part of the page that answers the question.
    """
    ordered = _clean_site(4)
    skipped = [
        _page(
            url=p.url, normalized_url=p.normalized_url, canonical_url=p.canonical_url,
            title=p.title, meta_description=p.meta_description, crawl_depth=p.crawl_depth,
            h1_count=1, heading_order_valid=False,
        )
        for p in ordered
    ]
    ordered_score, skipped_score = _score(ordered), _score(skipped)
    assert (
        skipped_score.evidence["geo"]["components"]["ai_readable_structure"]
        < ordered_score.evidence["geo"]["components"]["ai_readable_structure"]
    )
    assert skipped_score.geo_score < ordered_score.geo_score


def test_shared_signals_are_measured_once() -> None:
    """GEO's fact density and ACRS's are the same measurement. Computing them
    separately is how two sections of one report end up printing different
    numbers under the same name."""
    pages = _clean_site()
    for i, p in enumerate(pages):
        p.statistic_count = 3 if i < 3 else 0
    score = _score(pages)
    assert score.evidence["geo"]["components"]["fact_density"] == score.evidence["acrs"]["fact_density"]
    assert (
        score.evidence["aeo"]["components"]["passage_extraction"]
        == score.evidence["acrs"]["passage_extractability"]
    )


# --------------------------------------------------------------------------
# Authority — SEO's smallest component, and the one most often unmeasurable
# --------------------------------------------------------------------------


def test_authority_score_absent_without_any_referring_domains() -> None:
    """Zero referring domains in Spy's own index must never read as a
    confident low score; it means "no evidence yet", not "genuinely has no
    backlinks" (§3)."""
    score = _score(_clean_site())
    assert score.authority_score is None
    assert score.evidence["authority"]["referring_domains"] == 0
    assert "authority" not in score.evidence["seo"]["weights_used"]


def test_authority_score_present_with_referring_domains() -> None:
    pages = _clean_site()
    for p in pages:
        p.internal_pagerank = 50.0
    score = _score(pages, referring_domains=5, total_backlinks=12)
    assert score.authority_score is not None and score.authority_score > 0
    assert score.evidence["authority"]["referring_domains"] == 5
    assert score.evidence["authority"]["total_backlinks"] == 12
    assert "authority" in score.evidence["seo"]["weights_used"]


def test_authority_score_increases_with_more_referring_domains() -> None:
    pages = _clean_site()
    for p in pages:
        p.internal_pagerank = 50.0
    few = _score(pages, referring_domains=1, total_backlinks=1)
    many = _score(pages, referring_domains=40, total_backlinks=100)
    assert many.authority_score > few.authority_score


def test_authority_score_rewards_higher_internal_pagerank() -> None:
    low_pages, high_pages = _clean_site(), _clean_site()
    for p in low_pages:
        p.internal_pagerank = 5.0
    for p in high_pages:
        p.internal_pagerank = 90.0
    low = _score(low_pages, referring_domains=5, total_backlinks=5)
    high = _score(high_pages, referring_domains=5, total_backlinks=5)
    assert high.authority_score > low.authority_score
