"""§28 crawl politeness — robots.txt parsing and sitemap discovery.

All fetches go through the SSRF-guarded SafeFetcher (§107); this module adds
no second HTTP client.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin

from protego import Protego

from app.core.net.safe_client import SafeFetcher


@dataclass
class RobotsPolicy:
    parser: Protego | None
    sitemap_urls: list[str]
    crawl_delay: float | None
    found: bool = False

    def is_allowed(self, url: str, user_agent: str) -> bool:
        if self.parser is None:
            return True
        return self.parser.can_fetch(url, user_agent)

    def disallows_everything(self, origin: str, user_agent: str) -> bool:
        """A blanket `Disallow: /` — detected by checking both the root and
        an arbitrary, certainly-nonexistent path: if a made-up path is also
        blocked, that's a site-wide block rather than a rule targeting a
        real, specific path.
        """
        if self.parser is None:
            return False
        probe = origin.rstrip("/") + "/__spy_disallow_probe_3f9a2b__"
        return not self.is_allowed(origin + "/", user_agent) and not self.is_allowed(probe, user_agent)


async def fetch_robots_policy(fetcher: SafeFetcher, *, origin: str, user_agent: str) -> RobotsPolicy:
    robots_url = urljoin(origin + "/", "robots.txt")
    try:
        result = await fetcher.fetch(robots_url)
    except Exception:  # noqa: BLE001 - unreachable robots.txt => treat as "allow all"
        return RobotsPolicy(parser=None, sitemap_urls=[], crawl_delay=None, found=False)

    if result.response.status_code >= 400:
        return RobotsPolicy(parser=None, sitemap_urls=[], crawl_delay=None, found=False)

    body = result.response.text
    parser = Protego.parse(body)
    sitemaps = list(parser.sitemaps) if parser.sitemaps else []
    delay = parser.crawl_delay(user_agent)

    return RobotsPolicy(parser=parser, sitemap_urls=sitemaps, crawl_delay=delay, found=True)


MAX_SITEMAP_DOCUMENTS = 12


async def discover_sitemap_urls(
    fetcher: SafeFetcher,
    *,
    origin: str,
    robots_sitemaps: list[str],
    max_urls: int,
    max_documents: int = MAX_SITEMAP_DOCUMENTS,
) -> list[str]:
    """Best-effort sitemap discovery: robots.txt-declared sitemaps first,
    falling back to the conventional /sitemap.xml path.

    A <sitemapindex> is expanded into the sitemaps it points at, which is
    how any site with per-language or per-section sitemaps publishes them
    — treating the index as unparseable meant those sites looked like they
    had no sitemap at all, and every page they did publish came back
    `from_sitemap = False`.

    Expansion is breadth-first and bounded two ways so a hostile or merely
    enormous index can't turn one audit into thousands of fetches:
    `max_documents` caps how many sitemap files are retrieved in total, and
    `max_urls` caps the URLs returned. Already-seen sitemap URLs are
    skipped, so an index that references itself terminates.
    """
    import lxml.etree as ET

    queue: deque[str] = deque((robots_sitemaps or [urljoin(origin + "/", "sitemap.xml")])[:5])
    seen: set[str] = set()
    urls: list[str] = []
    documents_fetched = 0

    while queue and documents_fetched < max_documents and len(urls) < max_urls:
        sitemap_url = queue.popleft()
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)

        try:
            result = await fetcher.fetch(sitemap_url)
        except Exception:  # noqa: BLE001
            continue
        documents_fetched += 1
        if result.response.status_code != 200:
            continue
        try:
            root = ET.fromstring(result.response.content)
        except ET.XMLSyntaxError:
            continue

        container = ET.QName(root).localname
        if container not in ("urlset", "sitemapindex"):
            continue

        for element in root.iter():
            if ET.QName(element).localname != "loc" or not element.text:
                continue
            loc = element.text.strip()
            if not loc:
                continue
            if container == "urlset":
                urls.append(loc)
                if len(urls) >= max_urls:
                    return urls
            elif loc not in seen:
                queue.append(loc)

    return urls
