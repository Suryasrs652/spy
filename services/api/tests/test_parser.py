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


def test_hindi_question_heading_is_detected() -> None:
    """The real defect this guards: a Hindi translation of an English
    question-phrased heading carries its question particle ("क्यों", why)
    mid-sentence, before the verb — Hindi is SOV, so the particle is never
    at the start. A start-anchored English regex can never find it.
    Verified against the live translation of
    spilanthstudio.com/insights/what-makes-generated-footage-look-cheap.html.
    """
    result = _parse("<h1>जनरेटेड फ़ुटेज सस्ता क्यों दिखता है</h1>")
    assert result.question_heading_count == 1


def test_tamil_and_telugu_question_headings_are_detected() -> None:
    result = _parse("<h2>இது எப்படி வேலை செய்கிறது</h2><h2>ఇది ఎలా పని చేస్తుంది</h2>")
    assert result.question_heading_count == 2


def test_a_devanagari_heading_with_no_question_particle_is_not_counted() -> None:
    """The particle list is narrow on purpose — this must not turn into "any
    Devanagari heading counts", or it stops meaning anything."""
    result = _parse("<h2>व्यावसायिक विज्ञापन: त्वरित उत्तर</h2>")
    assert result.question_heading_count == 0


def test_a_latin_heading_is_unaffected_by_the_indic_particle_list() -> None:
    """Script-gating exists so a coincidental substring match can't fire
    outside the script it belongs to."""
    result = _parse("<h2>Our Services</h2><h2>How AI video generation works</h2>")
    assert result.question_heading_count == 1


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
    """WCAG Technique H67: a present-but-empty alt="" is, by itself, the
    complete and correct way to mark an image decorative — no additional
    aria-hidden or role="presentation" is required by the standard, or by
    any real accessibility checker. Counting alt="" as missing pushes
    authors to describe images that should stay silent — worse for the
    people alt text is for. Only a genuinely absent alt attribute is
    "missing".
    """
    body = (
        '<img src="a.png" alt="A described photograph">'
        '<img src="spacer.png" alt="" aria-hidden="true">'
        '<img src="flourish.png" alt="" role="presentation">'
        '<img src="logo.png" alt="">'           # bare alt="" — valid, not flagged
        '<img src="nope.png">'                  # no alt at all — flagged
    )
    result = _parse(body)
    assert result.images_total == 5
    assert result.images_missing_alt == 1


def test_a_bare_empty_alt_repeated_across_a_page_is_never_flagged() -> None:
    """The exact real-world shape this guards: spilanthstudio.com repeats
    one decorative logo image (bare alt="", no aria-hidden/role marker) as
    a nav-toggle icon on every page — 73 instances sitewide. None of them
    are missing alt text; the alt attribute is there and correctly empty.
    """
    body = '<img src="logo.png" alt="">' * 5 + '<img src="hero.jpg" alt="A director framing a shot">'
    result = _parse(body)
    assert result.images_total == 6
    assert result.images_missing_alt == 0


def test_width_height_is_still_checked_on_a_decorative_image() -> None:
    """Layout shift doesn't care whether an image is decorative — dropping
    the old aria-hidden/role early-exit must not accidentally exempt these
    images from the CLS check too."""
    result = _parse('<img src="spacer.png" alt="" aria-hidden="true">')
    assert result.images_missing_dimensions == 1


def test_a_br_split_headline_is_not_glued_into_one_word() -> None:
    """`<h1>Commercial<br>Ads</h1>` is a common two-line headline pattern —
    verified on spilanthstudio.com/services/commercial-ads.html, whose stored
    h1 read "CommercialAds" before this fix because a bare <br> carries no
    text node for get_text() to insert a boundary at."""
    result = _parse("<h1>Commercial<br>Ads</h1>")
    assert result.h1 == "Commercial Ads"


def test_a_br_split_heading_below_h1_is_also_fixed() -> None:
    """Same fix, same call site pattern — not just h1."""
    result = _parse("<h2>Our<br>Work</h2>")
    assert result.heading_sequence == ["h2"]  # sanity: one heading present
    # h2 text isn't stored on ParsedPage directly; confirm via question
    # detection instead, which reads the same _text_of() extraction.
    result2 = _parse("<h2>क्या<br>है</h2>")  # "what is" split across <br>
    assert result2.question_heading_count == 1


def test_ordinary_single_line_headings_are_unaffected() -> None:
    """The fix must not introduce a space where the source has none — only
    across an element boundary that previously had nothing between it."""
    result = _parse("<h1>Commercial Ads</h1>")
    assert result.h1 == "Commercial Ads"


def test_anchor_text_across_an_inline_tag_is_also_joined() -> None:
    """The same get_text()-with-no-separator bug affects anchor text
    whenever a link wraps a <br> or an inline element — same fix, same call
    site pattern."""
    result = _parse('<a href="/x">Read<br>more</a>')
    assert result.links[0].anchor_text == "Read more"
