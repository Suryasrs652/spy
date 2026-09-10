"""§27 URL normalization — pure, no DB/network needed."""
from __future__ import annotations

import pytest

from app.modules.crawler.normalize import canonical_origin, normalize_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://Example.com/Page#section", "https://example.com/Page"),
        ("http://example.com:80/a/b/", "http://example.com/a/b/"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/a/./b/../c", "https://example.com/a/c"),
        ("https://example.com/a%7eb", "https://example.com/a~b"),
        ("https://example.com/page?utm_source=x&b=2&a=1", "https://example.com/page?a=1&b=2"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/page?fbclid=123", "https://example.com/page"),
        ("https://example.com//a//b", "https://example.com/a/b"),
        ("https://EXAMPLE.com:443/x?Z=1&A=2", "https://example.com/x?A=2&Z=1"),
    ],
)
def test_normalize_url(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalize_idna_punycode() -> None:
    assert normalize_url("https://XN--EXAMPLE.com/a") == "https://xn--example.com/a"


def test_normalize_is_idempotent() -> None:
    url = "https://Example.com/A/./B/../C?utm_source=x&b=2&a=1#frag"
    once = normalize_url(url)
    twice = normalize_url(once)
    assert once == twice


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://Example.com:443/some/path?x=1", "https://example.com"),
        ("http://example.com/", "http://example.com"),
        ("https://example.com:8443/a", "https://example.com:8443"),
    ],
)
def test_canonical_origin(url: str, expected: str) -> None:
    assert canonical_origin(url) == expected
