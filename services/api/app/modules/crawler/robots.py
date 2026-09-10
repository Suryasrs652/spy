"""§28 crawl politeness — robots.txt parsing and sitemap discovery.

All fetches go through the SSRF-guarded SafeFetcher (§107); this module adds
no second HTTP client.
"""
from __future__ import annotations

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


async def discover_sitemap_urls(
    fetcher: SafeFetcher, *, origin: str, robots_sitemaps: list[str], max_urls: int
) -> list[str]:
    """Best-effort sitemap discovery: robots.txt-declared sitemaps first,
    falling back to the conventional /sitemap.xml path. Only plain
    <urlset> sitemaps are parsed for M1 — a <sitemapindex> pointing at
    further sitemaps is noted but not recursively expanded, to bound worst-
    case fetch volume on a single audit.
    """
    import lxml.etree as ET

    candidates = robots_sitemaps or [urljoin(origin + "/", "sitemap.xml")]
    urls: list[str] = []

    for sitemap_url in candidates[:5]:
        try:
            result = await fetcher.fetch(sitemap_url)
        except Exception:  # noqa: BLE001
            continue
        if result.response.status_code != 200:
            continue
        try:
            root = ET.fromstring(result.response.content)
        except ET.XMLSyntaxError:
            continue

        tag = ET.QName(root).localname
        if tag == "urlset":
            for loc in root.iter():
                if ET.QName(loc).localname == "loc" and loc.text:
                    urls.append(loc.text.strip())
                    if len(urls) >= max_urls:
                        return urls
        # sitemapindex: recording is out of scope for M1; the homepage BFS
        # crawl still discovers the same pages via on-page links.

    return urls
