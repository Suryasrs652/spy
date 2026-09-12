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


def _render(pages, links=None, referring_domains=0):
    score = compute_spy_score(
        pages=pages, findings=run_all_rules(pages, links or []), urls_processed=len(pages),
        links=links, referring_domains=referring_domains,
        total_backlinks=referring_domains * 2,
    )
    html = render_audit_report_html(
        audit=_audit(score),
        project=SimpleNamespace(domain="example.com", canonical_origin="https://example.com"),
        issues=[], recommendations=[],
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
