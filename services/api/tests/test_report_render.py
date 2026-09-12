"""The audit report template, rendered against real score evidence.

This existed untested until a v2 audit failed in production on
`'dict object' has no attribute 'not_measured'` — a Jinja expression that is
fine whenever the key happens to be present and raises when it isn't. The
template reads a JSONB blob whose shape varies by exactly that kind of
optional key, so the cases below are the shapes it has to survive: every
component measured, components missing, and nothing scoreable at all.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.modules.reports.render import render_audit_report_html
from app.modules.scoring.spy_score import compute_spy_score
from app.modules.seo.rules import run_all_rules
from tests.test_scoring import _broken_site, _citation_links, _clean_site


def _audit(score) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        spy_score=score.spy_score, seo_score=score.seo_score,
        aeo_score=score.aeo_score, geo_score=score.geo_score, acrs_score=score.acrs_score,
        technical_score=score.technical_score, onpage_score=score.onpage_score,
        content_score=score.content_score, internal_links_score=score.internal_links_score,
        structured_data_score=score.structured_data_score,
        performance_score=score.performance_score, authority_score=score.authority_score,
        confidence=score.confidence, score_version=score.score_version, evidence=score.evidence,
    )


def _issue(rule_id, *, category, severity, affected, title):
    """The shape the report reads off an AuditIssue row."""
    return SimpleNamespace(
        rule_id=rule_id, category=category, severity=severity, affected_count=affected,
        title=title, description="Because of reasons.", recommendation="Fix it.",
        score_impact=-1.0, confidence=1.0, validated=None, validation_note=None,
    )


def _render(pages, links=None, referring_domains=0, issues=None):
    score = compute_spy_score(
        pages=pages, findings=run_all_rules(pages, links or []), urls_processed=len(pages),
        links=links, referring_domains=referring_domains,
        total_backlinks=referring_domains * 2,
    )
    html = render_audit_report_html(
        audit=_audit(score),
        project=SimpleNamespace(domain="example.com", canonical_origin="https://example.com"),
        issues=issues or [], recommendations=[],
    )
    return score, html


def test_report_renders_every_section_for_a_fully_scored_site() -> None:
    pages = _clean_site()
    _score, html = _render(pages, links=_citation_links(pages))
    for heading in (
        "Overall Digital Search Score", "SEO breakdown", "AEO breakdown",
        "GEO breakdown", "What was not measured",
    ):
        assert heading in html, f"missing section: {heading}"


def test_report_renders_when_an_optional_evidence_key_is_absent() -> None:
    """`not_measured` only appears on the AEO block when something actually
    went unmeasured. The template has to read it either way — this is the
    exact expression that took a live audit down."""
    pages = _clean_site()
    score, html = _render(pages, links=_citation_links(pages))
    assert "not_measured" not in score.evidence["aeo"], "fixture no longer covers the absent-key case"
    assert "Overall Digital Search Score" in html


def test_report_renders_when_nothing_was_scoreable() -> None:
    _score, html = _render(_broken_site())
    assert "Overall Digital Search Score" in html
    # AEO/GEO carry a `reason` rather than components here; the breakdown
    # tables are skipped rather than rendering empty.
    assert "AEO breakdown" not in html


def test_report_names_unmeasured_dimensions_rather_than_scoring_them_zero() -> None:
    pages = _clean_site()
    _score, html = _render(pages, links=_citation_links(pages))
    assert "original_information_gain" in html
    assert "Not measured" in html


def test_report_explains_an_absent_authority_score() -> None:
    """"N/A" on its own reads as a failure. The report has to say why."""
    pages = _clean_site()
    _score, html = _render(pages, links=_citation_links(pages))
    assert "not measured, not as zero" in html

    with_backlinks_score, with_backlinks_html = _render(
        pages, links=_citation_links(pages), referring_domains=5
    )
    assert with_backlinks_score.authority_score is not None
    assert "not measured, not as zero" not in with_backlinks_html


def test_report_carries_the_issue_counts_and_the_blockers() -> None:
    """These sections are derived inside the renderer rather than passed in,
    so the report and the API cannot disagree about the same audit."""
    pages = _clean_site()
    issues = [
        _issue("SEO_META_004", category="Metadata", severity="HIGH", affected=5,
               title="Missing meta description"),
        _issue("SEO_IMG_001", category="Images", severity="MEDIUM", affected=5,
               title="Images missing alt text"),
        _issue("SEO_SEC_010", category="Security", severity="LOW", affected=5,
               title="Missing Referrer-Policy header"),
    ]
    _score, html = _render(pages, links=_citation_links(pages), issues=issues)

    assert "What&rsquo;s wrong" in html or "What’s wrong" in html
    assert "Critical issues" in html
    assert "Opportunities" in html
    assert "things blocking growth" in html
    # A blocker drawn from a score component, which no rule produces.
    assert "checkable figures" in html or "named author" in html


def test_report_omits_the_blocker_section_when_nothing_is_blocking() -> None:
    """An empty numbered list under a confident heading reads as a bug. If
    nothing clears the threshold, the section is not rendered at all."""
    # Enough substantial pages to clear topical depth *and* breadth, plus
    # figures, dates, liftable prose and Q&A markup.
    pages = _clean_site(40)
    for page in pages:
        page.word_count = 1200
        page.statistic_count = 5
        page.has_publication_date = True
        page.paragraph_count, page.self_contained_paragraph_count = 4, 4
        page.schema_types = ["Organization", "FAQPage", "Service"]
    _score, html = _render(pages, links=_citation_links(pages))
    assert "blocking growth" not in html
