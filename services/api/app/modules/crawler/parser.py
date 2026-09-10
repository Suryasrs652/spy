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


@dataclass
class ExtractedLink:
    target_url: str
    anchor_text: str | None
    nofollow: bool
    ugc: bool
    sponsored: bool
    is_internal: bool


@dataclass
class ParsedPage:
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    h1_count: int = 0
    canonical_url: str | None = None
    robots_meta: str | None = None
    word_count: int = 0
    content_hash: str = ""
    html_hash: str = ""
    schema_blocks: list[dict] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    images_missing_alt: int = 0
    images_total: int = 0
    links: list[ExtractedLink] = field(default_factory=list)
    heading_sequence: list[str] = field(default_factory=list)
    mixed_content: bool = False


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

    h1_tags = soup.find_all("h1")
    result.h1_count = len(h1_tags)
    result.h1 = _clean_text(h1_tags[0].get_text()) if h1_tags else None
    result.heading_sequence = [tag.name for tag in soup.find_all(re.compile(r"^h[1-6]$"))]

    canonical_tag = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
    if canonical_tag and canonical_tag.get("href"):
        result.canonical_url = normalize_url(urljoin(page_url, canonical_tag["href"]))

    robots_tag = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    result.robots_meta = _clean_text(robots_tag.get("content") if robots_tag else None)

    # Visible text word count (drop script/style/noscript content).
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    body_text = soup.get_text(separator=" ")
    words = [w for w in _WHITESPACE_RE.split(body_text) if w]
    result.word_count = len(words)
    result.content_hash = hashlib.sha256(" ".join(words).lower().encode("utf-8")).hexdigest()

    for img in soup.find_all("img"):
        result.images_total += 1
        alt = img.get("alt")
        if alt is None or not alt.strip():
            result.images_missing_alt += 1

    _extract_schema(soup, result)
    result.links = _extract_links(soup, page_url=page_url, base_origin=base_origin)
    result.mixed_content = _has_mixed_content(soup, page_url)

    return result


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
            if isinstance(block, dict):
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
