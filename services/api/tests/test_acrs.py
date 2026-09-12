"""§ACRS — AI Citation Readiness.

Checks the parser's structural signals and the score composed from them.
The thing under test is whether a passage could be lifted and attributed,
not whether it is any good.
"""
from __future__ import annotations

import uuid

from app.modules.crawler.parser import parse_html
from app.modules.scoring.acrs import citation_probability, compute_acrs
from tests.test_scoring import _page

_BASE = "<html><head><title>T</title></head><body>{body}</body></html>"


def _parse(body: str):
    return parse_html(page_url="https://example.com/p", html=_BASE.format(body=body), base_origin="https://example.com")


# ── parser signals ───────────────────────────────────────────────────────

def test_checkable_figures_are_counted_as_statistics() -> None:
    result = _parse("<p>Conversion rose 42% after we cut load time to 1.2 seconds, saving $14,000.</p>")
    assert result.statistic_count >= 3


def test_incidental_digits_are_not_statistics() -> None:
    """A year or a street number is not evidence of anything."""
    result = _parse("<p>Founded in 2019 at 42 Anna Salai, we work with brands worldwide.</p>")
    assert result.statistic_count == 0


def test_publication_date_detected_from_time_element() -> None:
    assert _parse('<p>Words enough to count as a passage here.</p><time datetime="2026-01-04">Jan</time>').has_publication_date


def test_publication_date_detected_from_schema() -> None:
    body = '<script type="application/ld+json">{"@type":"BlogPosting","datePublished":"2026-01-04"}</script>'
    assert _parse(body).has_publication_date


def test_page_without_any_date_is_marked_undated() -> None:
    assert not _parse("<p>A paragraph carrying no temporal signal whatsoever here.</p>").has_publication_date


def test_self_contained_paragraph_is_counted() -> None:
    body = "<p>Spilanth Studio is an AI video production company based in Chennai.</p>"
    result = _parse(body)
    assert result.paragraph_count == 1
    assert result.self_contained_paragraph_count == 1


def test_paragraph_opening_with_a_back_reference_is_not_extractable() -> None:
    """It cannot be quoted alone — what "this" refers to is elsewhere."""
    body = "<p>This means the approach scales to far larger campaigns than before.</p>"
    result = _parse(body)
    assert result.paragraph_count == 1
    assert result.self_contained_paragraph_count == 0


def test_captions_are_not_treated_as_passages() -> None:
    assert _parse("<p>Read more</p><p>Our work</p>").paragraph_count == 0


# ── score ────────────────────────────────────────────────────────────────

def _citable(**kw):
    defaults = dict(
        statistic_count=4, has_publication_date=True, paragraph_count=10,
        self_contained_paragraph_count=8, has_author_byline=True,
        question_heading_count=2, schema_types=["Article", "Organization"],
    )
    defaults.update(kw)
    return _page(**defaults)


def test_a_citable_page_scores_far_above_a_marketing_page() -> None:
    citable = [_citable()]
    marketing = [
        _page(
            statistic_count=0, has_publication_date=False, paragraph_count=10,
            self_contained_paragraph_count=1, has_author_byline=False,
            question_heading_count=0, table_count=0, has_definition_list=False, schema_types=[],
        )
    ]
    high, _ = compute_acrs(citable)
    low, _ = compute_acrs(marketing)
    assert high > low
    assert high >= 70
    assert low <= 20


def test_evidence_names_what_it_cannot_measure() -> None:
    """Factual accuracy and information gain need a corpus and a judgement.
    Reporting them as unmeasured is the point, not an omission."""
    _, evidence = compute_acrs([_citable()])
    assert len(evidence["not_measured"]) == 2
    assert any("factual" in item for item in evidence["not_measured"])
    assert any("information_gain" in item for item in evidence["not_measured"])


def test_no_indexable_pages_reports_a_reason_not_a_zero() -> None:
    score, evidence = compute_acrs([_page(indexable=False)])
    assert score == 0.0
    assert "reason" in evidence


def test_outbound_citations_raise_source_attribution() -> None:
    """On a site too small to infer boilerplate from, every external link
    is taken at face value — see MIN_PAGES_FOR_BOILERPLATE_DETECTION."""
    from app.modules.crawler.models import PageLink

    page = _citable()
    link = PageLink(
        id=uuid.uuid4(), audit_id=uuid.uuid4(), source_page_id=page.id,
        target_url="https://another-domain.example/research", is_internal=False,
    )
    without, _ = compute_acrs([page])
    with_citation, evidence = compute_acrs([page], [link])
    assert with_citation > without
    assert evidence["source_attribution"] == 100.0


def test_citation_probability_bands() -> None:
    assert citation_probability(80) == "VERY_HIGH"
    assert citation_probability(60) == "HIGH"
    assert citation_probability(40) == "MEDIUM"
    assert citation_probability(10) == "LOW"


def test_sitewide_footer_links_do_not_count_as_citations() -> None:
    """One social profile in a shared footer appears on every page. Counting
    it would score a site 100% for citing its own LinkedIn.
    """
    from app.modules.crawler.models import PageLink

    pages = [_citable(url=f"https://example.com/{i}") for i in range(10)]
    audit_id = uuid.uuid4()
    footer = [
        PageLink(
            id=uuid.uuid4(), audit_id=audit_id, source_page_id=p.id,
            target_url="https://www.linkedin.com/in/example/", is_internal=False,
        )
        for p in pages
    ]
    _, evidence = compute_acrs(pages, footer)
    assert evidence["source_attribution"] == 0.0

    # A source cited by one page is a real citation.
    footer.append(
        PageLink(
            id=uuid.uuid4(), audit_id=audit_id, source_page_id=pages[0].id,
            target_url="https://research.example.org/study", is_internal=False,
        )
    )
    _, evidence = compute_acrs(pages, footer)
    assert evidence["source_attribution"] == 10.0


def test_a_whatsapp_contact_link_does_not_count_as_a_citation() -> None:
    """Found on a real audit: a WhatsApp click-to-chat badge on four contact
    pages was the only external link on the entire site, and it inflated
    source_attribution from a true 0% to a false 5.7%. It's how a visitor
    reaches the business, not a source the page cites — same category as
    the mailto:/tel: links that never become PageLink rows at all."""
    from app.modules.crawler.models import PageLink

    pages = [_citable(url=f"https://example.com/{i}") for i in range(10)]
    audit_id = uuid.uuid4()
    contact_page = pages[0]
    whatsapp = PageLink(
        id=uuid.uuid4(), audit_id=audit_id, source_page_id=contact_page.id,
        target_url="https://wa.me/919999999999", is_internal=False,
    )
    _, evidence = compute_acrs(pages, [whatsapp])
    assert evidence["source_attribution"] == 0.0


def test_a_real_citation_still_counts_alongside_an_excluded_contact_link() -> None:
    from app.modules.crawler.models import PageLink

    page = _citable()
    audit_id = uuid.uuid4()
    links = [
        PageLink(
            id=uuid.uuid4(), audit_id=audit_id, source_page_id=page.id,
            target_url="https://wa.me/919999999999", is_internal=False,
        ),
        PageLink(
            id=uuid.uuid4(), audit_id=audit_id, source_page_id=page.id,
            target_url="https://research.example.org/study", is_internal=False,
        ),
    ]
    _, evidence = compute_acrs([page], links)
    assert evidence["source_attribution"] == 100.0
