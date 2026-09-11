"""Parses one fetched HTML response into the structured fields stored on
`crawl_pages` (§67) and extracts outbound links for `page_links` (§68).

Pure function of (url, status_code, headers, html_bytes) — no I/O — so it is
unit-testable on fixture HTML without a network or a browser.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.modules.crawler.normalize import normalize_url

_WHITESPACE_RE = re.compile(r"\s+")

# Alt text that carries no real information — usually the filename or a
# CMS/theme default left in place, not a description of the image (§23
# Images: "non-descriptive alt text").
_GENERIC_ALT_RE = re.compile(
    r"^(image|img|photo|picture|untitled|dsc[_-]?\d+|screenshot|icon)?[\s_-]*\d*\.?(jpe?g|png|gif|webp|svg)?$",
    re.I,
)

# §48 AEO "question coverage": a heading counts as question-style if it's
# phrased as a natural-language question, not just any heading ending in "?".
_QUESTION_START_RE = re.compile(
    r"^(who|what|when|where|why|how|which|can|does|do|is|are|should|will)\b", re.I
)


@dataclass
class ExtractedLink:
    target_url: str
    anchor_text: str | None
    nofollow: bool
    ugc: bool
    sponsored: bool
    is_internal: bool


@dataclass
class HreflangTag:
    lang: str
    url: str


@dataclass
class ParsedPage:
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    h1_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    heading_order_valid: bool = True
    canonical_url: str | None = None
    robots_meta: str | None = None
    word_count: int = 0
    content_hash: str = ""
    html_hash: str = ""
    schema_blocks: list[dict] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    images_missing_alt: int = 0
    images_missing_dimensions: int = 0
    images_generic_alt: int = 0
    images_total: int = 0
    links: list[ExtractedLink] = field(default_factory=list)
    heading_sequence: list[str] = field(default_factory=list)
    mixed_content: bool = False
    has_og_title: bool = False
    has_og_description: bool = False
    has_og_image: bool = False
    has_twitter_card: bool = False
    has_viewport_meta: bool = False
    has_charset_meta: bool = False
    has_favicon: bool = False
    html_lang: str | None = None
    hreflang_tags: list[HreflangTag] = field(default_factory=list)
    has_insecure_form_action: bool = False
    word_frequency_top_ratio: float = 0.0
    question_heading_count: int = 0
    list_count: int = 0
    table_count: int = 0
    has_definition_list: bool = False
    has_author_byline: bool = False


def _clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    return cleaned or None


def parse_html(*, page_url: str, html: str, base_origin: str) -> ParsedPage:
    soup = BeautifulSoup(html, "lxml")
    result = ParsedPage()

    result.html_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()

    title_tag = soup.find("title")
    result.title = _clean_text(title_tag.get_text() if title_tag else None)

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    result.meta_description = _clean_text(meta_desc.get("content") if meta_desc else None)

    _extract_headings(soup, result)

    canonical_tag = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
    if canonical_tag and canonical_tag.get("href"):
        result.canonical_url = normalize_url(urljoin(page_url, canonical_tag["href"]))

    robots_tag = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    result.robots_meta = _clean_text(robots_tag.get("content") if robots_tag else None)

    _extract_social_tags(soup, result)
    _extract_page_setup_tags(soup, page_url, result)
    _extract_hreflang(soup, page_url, result)

    html_el = soup.find("html")
    if html_el and html_el.get("lang"):
        result.html_lang = html_el["lang"].strip() or None

    # JSON-LD lives in <script> tags, so it has to be read before the
    # decompose() below removes them — it used to run after, which meant
    # structured data was silently never detected on any site.
    _extract_schema(soup, result)

    # Visible text word count (drop script/style/noscript content) — do this
    # AFTER the tag-based extraction above since it destructively removes
    # <script>/<style> nodes.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    body_text = soup.get_text(separator=" ")
    words = [w for w in _WHITESPACE_RE.split(body_text) if w]
    result.word_count = len(words)
    result.content_hash = hashlib.sha256(" ".join(words).lower().encode("utf-8")).hexdigest()
    result.word_frequency_top_ratio = _top_word_ratio(words)

    _extract_images(soup, result)
    result.links = _extract_links(soup, page_url=page_url, base_origin=base_origin)
    result.mixed_content = _has_mixed_content(soup, page_url)
    result.has_insecure_form_action = _has_insecure_form_action(soup, page_url)
    result.list_count = len(soup.find_all(["ul", "ol"]))
    result.table_count = len(soup.find_all("table"))
    result.has_definition_list = any(dl.find("dt") and dl.find("dd") for dl in soup.find_all("dl"))
    result.has_author_byline = _has_author_byline(soup)

    return result


def _extract_headings(soup: BeautifulSoup, result: ParsedPage) -> None:
    h1_tags = soup.find_all("h1")
    result.h1_count = len(h1_tags)
    result.h1 = _clean_text(h1_tags[0].get_text()) if h1_tags else None
    result.h2_count = len(soup.find_all("h2"))
    result.h3_count = len(soup.find_all("h3"))

    heading_tags = soup.find_all(re.compile(r"^h[1-6]$"))
    sequence = [tag.name for tag in heading_tags]
    result.heading_sequence = sequence

    for tag in heading_tags:
        text = (_clean_text(tag.get_text()) or "").strip()
        if not text:
            continue
        if text.endswith("?") or _QUESTION_START_RE.match(text):
            result.question_heading_count += 1

    # A heading hierarchy is "valid" if it never jumps down more than one
    # level at a time (e.g. H2 -> H4 with no H3 in between is a skip).
    valid = True
    last_level = 0
    for tag_name in sequence:
        level = int(tag_name[1])
        if last_level and level > last_level + 1:
            valid = False
            break
        last_level = level
    result.heading_order_valid = valid


def _extract_social_tags(soup: BeautifulSoup, result: ParsedPage) -> None:
    def has_meta_property(prop: str) -> bool:
        tag = soup.find("meta", attrs={"property": prop})
        return bool(tag and tag.get("content", "").strip())

    result.has_og_title = has_meta_property("og:title")
    result.has_og_description = has_meta_property("og:description")
    result.has_og_image = has_meta_property("og:image")

    twitter_card = soup.find("meta", attrs={"name": re.compile("^twitter:card$", re.I)})
    result.has_twitter_card = bool(twitter_card and twitter_card.get("content", "").strip())


def _extract_page_setup_tags(soup: BeautifulSoup, page_url: str, result: ParsedPage) -> None:
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    result.has_viewport_meta = bool(viewport and viewport.get("content", "").strip())

    charset_meta = soup.find("meta", attrs={"charset": True})
    charset_http_equiv = soup.find(
        "meta", attrs={"http-equiv": re.compile("^content-type$", re.I)}
    )
    result.has_charset_meta = bool(charset_meta or charset_http_equiv)

    for rel_value in ("icon", "shortcut icon", "apple-touch-icon"):
        if soup.find("link", attrs={"rel": re.compile(f"^{re.escape(rel_value)}$", re.I)}):
            result.has_favicon = True
            break


def _extract_hreflang(soup: BeautifulSoup, page_url: str, result: ParsedPage) -> None:
    for tag in soup.find_all("link", attrs={"rel": re.compile("^alternate$", re.I)}):
        lang = tag.get("hreflang")
        href = tag.get("href")
        if not lang or not href:
            continue
        try:
            absolute = normalize_url(urljoin(page_url, href))
        except Exception:  # noqa: BLE001
            continue
        result.hreflang_tags.append(HreflangTag(lang=lang.strip(), url=absolute))


def _extract_images(soup: BeautifulSoup, result: ParsedPage) -> None:
    for img in soup.find_all("img"):
        result.images_total += 1
        alt = img.get("alt")
        # An explicitly decorative image is *supposed* to carry alt="" —
        # WCAG asks for exactly that so screen readers skip it. Counting it
        # as a missing alt tells authors to describe images that should stay
        # silent, which is actively worse for the people alt text exists
        # for. Only the explicit markers count; a bare alt="" is still
        # ambiguous enough to flag.
        if img.get("aria-hidden") == "true" or img.get("role") == "presentation":
            continue
        if alt is None or not alt.strip():
            result.images_missing_alt += 1
        elif _GENERIC_ALT_RE.match(alt.strip()):
            result.images_generic_alt += 1

        if not (img.get("width") and img.get("height")):
            result.images_missing_dimensions += 1


def _top_word_ratio(words: list[str]) -> float:
    """Fraction of all words that are the single most-repeated word — a
    crude, purely-statistical proxy for keyword stuffing (§23 Content)
    that needs no NLP: a normal page's most common word (excluding nothing,
    stopwords included) rarely exceeds a few percent of total words; a
    stuffed page spikes noticeably.
    """
    if len(words) < 20:
        return 0.0
    from collections import Counter

    counts = Counter(w.lower() for w in words if len(w) > 2)
    if not counts:
        return 0.0
    _, top_count = counts.most_common(1)[0]
    return round(top_count / len(words), 4)


def _has_mixed_content(soup: BeautifulSoup, page_url: str) -> bool:
    """§104/§107 security check: an https page pulling any sub-resource
    over plain http (§107's own SSRF fetching is unrelated to this — this
    is about what the *page itself* tells a visiting browser to load).
    """
    if not page_url.lower().startswith("https://"):
        return False
    for tag, attr in (("img", "src"), ("script", "src"), ("link", "href"), ("iframe", "src")):
        for el in soup.find_all(tag):
            value = el.get(attr, "")
            if value.lower().startswith("http://"):
                return True
    return False


def _has_insecure_form_action(soup: BeautifulSoup, page_url: str) -> bool:
    if not page_url.lower().startswith("https://"):
        return False
    for form in soup.find_all("form"):
        action = form.get("action", "")
        if action.lower().startswith("http://"):
            return True
    return False


_BYLINE_HINT_RE = re.compile(r"\b(author|byline)\b", re.I)


def _has_author_byline(soup: BeautifulSoup) -> bool:
    """§48 "source attribution" signal: a deterministic, structural check for
    authorship markup — never guesses a name from free text. Covers the three
    common conventions: a <meta name="author">, rel="author" (HTML5 link
    relation for the page's author), and itemprop="author" (schema.org
    microdata) or an author/byline class hook used by most CMS themes.
    """
    if soup.find("meta", attrs={"name": re.compile("^author$", re.I)}):
        return True
    if soup.find(attrs={"itemprop": re.compile("^author$", re.I)}):
        return True
    for tag in soup.find_all(attrs={"rel": True}):
        rel = tag.get("rel") or []
        rel_values = rel if isinstance(rel, list) else rel.split()
        if any(v.lower() == "author" for v in rel_values):
            return True
    return bool(soup.find(class_=_BYLINE_HINT_RE) or soup.find(id=_BYLINE_HINT_RE))


def _extract_schema(soup: BeautifulSoup, result: ParsedPage) -> None:
    import json

    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            result.schema_errors.append(str(exc))
            continue
        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            # `@graph` is the standard container for "several entities in
            # one script tag" and is what Yoast, RankMath and most
            # hand-rolled implementations emit. The wrapper itself carries
            # no @type, so treating it as a block made every @graph site
            # read as having no structured data at all.
            graph = block.get("@graph")
            if isinstance(graph, list):
                result.schema_blocks.extend(node for node in graph if isinstance(node, dict))
                if "@type" in block:
                    result.schema_blocks.append(block)
            else:
                result.schema_blocks.append(block)


def _extract_links(soup: BeautifulSoup, *, page_url: str, base_origin: str) -> list[ExtractedLink]:
    links: list[ExtractedLink] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        absolute = urljoin(page_url, href)
        if not absolute.lower().startswith(("http://", "https://")):
            continue

        try:
            normalized = normalize_url(absolute)
        except Exception:  # noqa: BLE001 - malformed href, skip rather than crash the crawl
            continue

        if normalized in seen:
            continue
        seen.add(normalized)

        rel = (a.get("rel") or [])
        rel_values = {r.lower() for r in (rel if isinstance(rel, list) else rel.split())}

        links.append(
            ExtractedLink(
                target_url=normalized,
                anchor_text=_clean_text(a.get_text()),
                nofollow="nofollow" in rel_values,
                ugc="ugc" in rel_values,
                sponsored="sponsored" in rel_values,
                is_internal=normalized.startswith(base_origin),
            )
        )

    return links
