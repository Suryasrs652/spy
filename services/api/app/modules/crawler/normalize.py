"""§27 URL normalization.

Defines page identity for the whole system — the crawler's visited-set, the
`crawl_pages.normalized_url` column, and the `projects.canonical_origin`
uniqueness constraint all key off this module. A bug here silently corrupts
every downstream count (duplicate-content detection, orphan-page detection,
internal PageRank), so it is pure, dependency-light, and has its own large
unit-test table (tests/test_normalize.py) rather than being exercised only
indirectly through the crawler.
"""
from __future__ import annotations

from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)

# Params that carry no identity information for the underlying page — safe
# to drop when computing the canonical/normalized form. The *original* URL
# (with these intact) is always preserved separately (crawl_pages.url).
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "msclkid", "mc_cid", "mc_eid", "igshid",
}

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _normalize_host(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    if hostname.isascii():
        return hostname
    import idna

    try:
        return idna.encode(hostname).decode("ascii")
    except idna.IDNAError:
        # Already-punycode or malformed — pass through lowercased rather
        # than fail normalization outright.
        return hostname


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 §5.2.4 dot-segment removal."""
    if not path:
        return path

    is_absolute = path.startswith("/")
    trailing_slash = path.endswith("/") and path != "/"

    segments: list[str] = []
    for part in path.split("/"):
        if part == "..":
            if segments:
                segments.pop()
        elif part == "." or part == "":
            continue
        else:
            segments.append(part)

    result = "/".join(segments)
    if is_absolute:
        result = "/" + result
    if trailing_slash and not result.endswith("/"):
        result += "/"
    return result or "/"


def _normalize_percent_encoding(component: str) -> str:
    """Decode then re-encode so equivalent percent-escapes compare equal
    (e.g. `%7e` and `~` and `%7E` all become the same thing), without
    double-encoding characters that must stay escaped.
    """
    return quote(unquote(component), safe="/-._~!$&'()*+,;=:@")


def normalize_url(url: str, *, strip_tracking: bool = True) -> str:
    """Return the canonical form of `url` used for page-identity comparisons.

    The original URL string is never mutated in storage — callers keep both
    (`url` and `normalized_url` in `crawl_pages`).
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = _normalize_host(parts.hostname or "")

    port = parts.port
    default_port = _DEFAULT_PORTS.get(scheme)
    netloc = hostname
    if port is not None and port != default_port:
        netloc = f"{hostname}:{port}"

    path = _remove_dot_segments(parts.path or "/")
    path = _normalize_percent_encoding(path)
    if path == "":
        path = "/"

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if strip_tracking:
        query_pairs = [(k, v) for k, v in query_pairs if k.lower() not in _TRACKING_PARAMS]
    # Sort so param order never affects identity.
    query_pairs.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(query_pairs)

    # Fragment is always dropped — §27 "/page#section -> /page".
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_origin(url: str) -> str:
    """scheme://host[:port] only — used for `projects.canonical_origin`
    uniqueness (§63): two projects for the same origin are the same project.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = _normalize_host(parts.hostname or "")
    port = parts.port
    default_port = _DEFAULT_PORTS.get(scheme)
    netloc = hostname if port is None or port == default_port else f"{hostname}:{port}"
    return urlunsplit((scheme, netloc, "", "", ""))
