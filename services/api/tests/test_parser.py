"""§48/§49 AEO/GEO content-structure extraction — pure function of raw HTML,
no network or DB, unlike the rest of the crawler pipeline (§67's other
fields are only exercised indirectly via CrawlPage fixtures in
test_scoring.py/test_rules.py; these signals are new enough, and regex/
structure-dependent enough, to warrant testing directly against real HTML).
"""
from __future__ import annotations

from app.modules.crawler.parser import parse_html

_BASE = "<html><head><title>T</title></head><body>{body}</body></html>"


def _parse(body: str):
    return parse_html(page_url="https://example.com/page", html=_BASE.format(body=body), base_origin="https://example.com")


def test_question_style_headings_are_counted() -> None:
    result = _parse("<h2>What is SEO?</h2><h2>How does crawling work</h2><h2>Our Services</h2>")
    assert result.question_heading_count == 2


def test_no_question_headings_when_none_present() -> None:
    result = _parse("<h1>Welcome</h1><h2>Our Services</h2><h2>Pricing</h2>")
    assert result.question_heading_count == 0


def test_list_and_table_and_definition_list_counts() -> None:
    result = _parse(
        "<ul><li>a</li></ul><ol><li>b</li></ol>"
        "<table><tr><td>x</td></tr></table>"
        "<dl><dt>Term</dt><dd>Definition</dd></dl>"
    )
    assert result.list_count == 2
    assert result.table_count == 1
    assert result.has_definition_list is True


def test_empty_definition_list_not_counted() -> None:
    result = _parse("<dl></dl>")
    assert result.has_definition_list is False


def test_author_byline_via_meta_tag() -> None:
    result = _parse("<p>hello</p>")
    result_with_meta = parse_html(
        page_url="https://example.com/page",
        html='<html><head><title>T</title><meta name="author" content="Jane Doe"></head><body><p>hi</p></body></html>',
        base_origin="https://example.com",
    )
    assert result.has_author_byline is False
    assert result_with_meta.has_author_byline is True


def test_author_byline_via_byline_class() -> None:
    result = _parse('<div class="post-byline">By Jane Doe</div>')
    assert result.has_author_byline is True


def test_author_byline_via_itemprop() -> None:
    result = _parse('<span itemprop="author">Jane Doe</span>')
    assert result.has_author_byline is True


def test_author_byline_via_rel_author_link() -> None:
    result = _parse('<a href="/authors/jane" rel="author">Jane Doe</a>')
    assert result.has_author_byline is True


def test_no_byline_signal_present() -> None:
    result = _parse("<p>Just some ordinary paragraph text with no authorship markup.</p>")
    assert result.has_author_byline is False


def test_json_ld_graph_container_is_unwrapped() -> None:
    """`@graph` is how most real sites (Yoast, RankMath, hand-rolled) emit
    several entities from one script tag. The wrapper has no @type of its
    own, so treating it as a single block made every such site report zero
    structured data — and dragged its AEO/GEO scores down with it.
    """
    body = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"ProfessionalService","name":"Studio"},
      {"@type":"WebSite","name":"Site"},
      {"@type":"FAQPage"}
    ]}
    </script>
    """
    result = _parse(body)
    types = [b.get("@type") for b in result.schema_blocks]
    assert types == ["ProfessionalService", "WebSite", "FAQPage"]


def test_plain_json_ld_object_still_parses() -> None:
    body = '<script type="application/ld+json">{"@type":"Organization","name":"X"}</script>'
    result = _parse(body)
    assert [b.get("@type") for b in result.schema_blocks] == ["Organization"]


def test_decorative_images_are_not_counted_as_missing_alt() -> None:
    """WCAG asks for alt="" on decorative images so screen readers skip
    them. Counting that as a missing alt pushes authors to describe images
    that should stay silent — worse for the people alt text is for.
    """
    body = (
        '<img src="a.png" alt="A described photograph">'
        '<img src="spacer.png" alt="" aria-hidden="true">'
        '<img src="flourish.png" alt="" role="presentation">'
        '<img src="logo.png" alt="">'          # ambiguous — still flagged
        '<img src="nope.png">'                  # no alt at all — flagged
    )
    result = _parse(body)
    assert result.images_total == 5
    assert result.images_missing_alt == 2
