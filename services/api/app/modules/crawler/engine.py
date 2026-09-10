"""§26/§28/§29 — the crawl loop.

Strategy per §26: HTTP fetch first; browser rendering is a fallback used
only when JS_RENDER_ENABLED is on and the fetched HTML looks JS-dependent
(near-empty body with a script-heavy <head>) — never render every page.

Runs as a batched breadth-first search: each round fetches up to
`concurrency` frontier URLs at once via the SSRF-guarded SafeFetcher,
parses them, records pages/links, and enqueues newly-discovered internal
links for the next round. Bounded by `max_urls` (plan limit) and
`MAX_CRAWL_DEPTH_HARD` (safety cap independent of the rule-engine's
"warning" depth threshold).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

import structlog

from app.core.config import get_settings
from app.core.errors import BlockedTargetError
from app.core.net.safe_client import SafeFetcher
from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.crawler.normalize import normalize_url
from app.modules.crawler.parser import ParsedPage, parse_html
from app.modules.crawler.robots import discover_sitemap_urls, fetch_robots_policy

logger = structlog.get_logger(__name__)

MAX_CRAWL_DEPTH_HARD = 10
FETCH_TIMEOUT_SECONDS = 15.0


class CrawlFailure(Exception):
    """Raised for audit-ending failures (§30) — caught by the Celery task,
    which maps `code` onto Audit.failure_category/failure_code."""

    def __init__(self, code: str, category: str, message: str):
        super().__init__(message)
        self.code = code
        self.category = category
        self.message = message


@dataclass
class CrawlResult:
    pages: list[CrawlPage] = field(default_factory=list)
    links: list[PageLink] = field(default_factory=list)
    urls_discovered: int = 0
    urls_processed: int = 0


def _looks_js_dependent(html: str) -> bool:
    """Heuristic for the HTTP->Playwright fallback (§26): a very small
    rendered body alongside heavy script content usually means the real
    content is client-rendered.
    """
    lowered = html.lower()
    body_start = lowered.find("<body")
    visible_len = len(html) - body_start if body_start != -1 else len(html)
    script_count = lowered.count("<script")
    return visible_len < 800 and script_count >= 3


async def crawl_site(
    *,
    audit_id: uuid.UUID,
    project_id: uuid.UUID,
    origin: str,
    max_urls: int,
    on_progress=None,
) -> CrawlResult:
    settings = get_settings()
    fetcher = SafeFetcher(timeout=FETCH_TIMEOUT_SECONDS)
    result = CrawlResult()
    visited: set[str] = set()
    page_id_by_url: dict[str, uuid.UUID] = {}
    pending_links: list[tuple[str, str, "object"]] = []  # (source_url, target_url, ExtractedLink)

    try:
        policy = await fetch_robots_policy(fetcher, origin=origin, user_agent=settings.crawler_user_agent)

        seed_urls: list[str] = [origin + "/"]
        try:
            sitemap_urls = await discover_sitemap_urls(
                fetcher, origin=origin, robots_sitemaps=policy.sitemap_urls, max_urls=max_urls
            )
            seed_urls.extend(sitemap_urls)
        except Exception:  # noqa: BLE001 - sitemap discovery is best-effort
            logger.warning("sitemap_discovery_failed", audit_id=str(audit_id))

        frontier: list[tuple[str, int]] = []
        seen_frontier: set[str] = set()
        for u in seed_urls:
            try:
                n = normalize_url(u)
            except Exception:  # noqa: BLE001
                continue
            if n not in seen_frontier:
                seen_frontier.add(n)
                frontier.append((n, 0))

        result.urls_discovered = len(frontier)
        concurrency = settings.crawler_max_concurrency_per_host
        first_batch = True

        while frontier and len(visited) < max_urls:
            batch = frontier[:concurrency]
            frontier = frontier[concurrency:]

            batch = [(u, d) for u, d in batch if u not in visited and d <= MAX_CRAWL_DEPTH_HARD]
            if not batch:
                continue

            for u, _ in batch:
                visited.add(u)

            fetch_results = await asyncio.gather(
                *[_fetch_and_parse(fetcher, url, depth, origin, policy, settings.crawler_user_agent)
                  for url, depth in batch],
                return_exceptions=True,
            )

            for (url, depth), outcome in zip(batch, fetch_results):
                if isinstance(outcome, BlockedTargetError):
                    logger.warning("page_blocked", url=url, audit_id=str(audit_id))
                    continue
                if isinstance(outcome, Exception):
                    if first_batch and url == origin + "/":
                        raise _classify_fatal(outcome)
                    logger.info("page_fetch_error", url=url, error=str(outcome))
                    continue

                page, parsed, links = outcome
                page.audit_id = audit_id
                page.project_id = project_id
                page.crawl_depth = depth
                result.pages.append(page)
                page_id_by_url[url] = page.id
                result.urls_processed += 1

                if parsed is not None:
                    for link in links:
                        pending_links.append((url, link.target_url, link))
                        if (
                            link.is_internal
                            and link.target_url not in visited
                            and link.target_url not in seen_frontier
                            and len(visited) + len(frontier) < max_urls
                            and depth + 1 <= MAX_CRAWL_DEPTH_HARD
                        ):
                            seen_frontier.add(link.target_url)
                            frontier.append((link.target_url, depth + 1))
                            result.urls_discovered += 1

            first_batch = False
            if on_progress:
                await on_progress(result.urls_processed, result.urls_discovered)

        if result.urls_processed == 0:
            raise CrawlFailure("NO_CRAWLABLE_HTML", "TARGET_ERROR", "No crawlable HTML page was discovered.")

        status_by_url = {p.url: p.status_code for p in result.pages}
        for source_url, target_url, link in pending_links:
            result.links.append(
                PageLink(
                    audit_id=audit_id,
                    source_page_id=page_id_by_url.get(source_url),
                    target_url=target_url,
                    target_page_id=page_id_by_url.get(target_url),
                    anchor_text=link.anchor_text,
                    is_internal=link.is_internal,
                    nofollow=link.nofollow,
                    ugc=link.ugc,
                    sponsored=link.sponsored,
                    # Only known when the target was itself crawled this run
                    # (e.g. another internal page); an external or
                    # not-yet-visited target stays None (undetermined),
                    # rather than a possibly-stale guess.
                    status_code=status_by_url.get(target_url),
                )
            )

        return result
    finally:
        await fetcher.aclose()


async def _fetch_and_parse(fetcher, url, depth, origin, policy, user_agent):
    if not policy.is_allowed(url, user_agent):
        page = CrawlPage(
            id=uuid.uuid4(), url=url, normalized_url=url, status_code=None,
            robots_allowed=False, indexable=False, crawl_depth=depth,
        )
        return page, None, []

    start = time.perf_counter()
    fetch_result = await fetcher.fetch(url)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    response = fetch_result.response
    content_type = response.headers.get("content-type", "")
    is_html = "text/html" in content_type or content_type == ""

    page = CrawlPage(
        id=uuid.uuid4(),
        url=url,
        normalized_url=url,
        status_code=response.status_code,
        content_type=content_type.split(";")[0].strip() or None,
        robots_allowed=True,
        response_ms=elapsed_ms,
        html_size=len(response.content),
        crawl_depth=depth,
    )

    if not is_html or response.status_code >= 400:
        page.indexable = False
        return page, None, []

    html = response.text
    if get_settings().js_render_enabled and _looks_js_dependent(html):
        html = await _render_with_playwright(url) or html

    parsed: ParsedPage = parse_html(page_url=fetch_result.final_url, html=html, base_origin=origin)

    page.title = parsed.title
    page.meta_description = parsed.meta_description
    page.h1 = parsed.h1
    page.h1_count = parsed.h1_count
    page.canonical_url = parsed.canonical_url
    page.robots_meta = parsed.robots_meta
    page.word_count = parsed.word_count
    page.content_hash = parsed.content_hash
    page.html_hash = parsed.html_hash
    page.redirect_count = len(fetch_result.redirect_chain)
    page.images_total = parsed.images_total
    page.images_missing_alt = parsed.images_missing_alt
    page.has_schema = len(parsed.schema_blocks) > 0
    page.schema_types = _extract_schema_types(parsed.schema_blocks)
    page.schema_invalid = len(parsed.schema_errors) > 0
    page.mixed_content = parsed.mixed_content

    robots_meta_lower = (parsed.robots_meta or "").lower()
    page.indexable = "noindex" not in robots_meta_lower and response.status_code < 400

    return page, parsed, parsed.links


def _extract_schema_types(schema_blocks: list[dict]) -> list[str]:
    types: list[str] = []
    for block in schema_blocks:
        t = block.get("@type")
        if isinstance(t, str):
            types.append(t)
        elif isinstance(t, list):
            types.extend(str(x) for x in t)
    return types


async def _render_with_playwright(url: str) -> str | None:
    """JS-render fallback (§26) — only reached when JS_RENDER_ENABLED is on
    and the fast path looks JS-dependent. Uses the same Chromium runtime the
    PDF renderer uses (app/modules/reports/pdf.py).
    """
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=15000)
                return await page.content()
            finally:
                await browser.close()
    except Exception:  # noqa: BLE001 - fall back to the HTTP-fetched HTML
        logger.warning("playwright_render_failed", url=url, exc_info=True)
        return None


def _classify_fatal(exc: Exception) -> CrawlFailure:
    import ssl

    import httpx

    from app.core.net.safe_client import DnsResolutionError

    if isinstance(exc, DnsResolutionError):
        return CrawlFailure("DNS_FAILURE", "TARGET_ERROR", str(exc))
    if isinstance(exc, BlockedTargetError):
        return CrawlFailure("BLOCKED_TARGET", "USER_ERROR", str(exc))
    if isinstance(exc, httpx.ConnectTimeout | httpx.ReadTimeout | httpx.PoolTimeout):
        return CrawlFailure("TIMEOUT", "TARGET_ERROR", "The target site timed out.")
    if isinstance(exc, ssl.SSLError):
        return CrawlFailure("SSL_ERROR", "TARGET_ERROR", "The target site has an invalid TLS certificate.")
    if isinstance(exc, httpx.ConnectError):
        return CrawlFailure("UNREACHABLE", "TARGET_ERROR", "The target site could not be reached.")
    return CrawlFailure("WORKER_ERROR", "SYSTEM_ERROR", f"Unexpected crawler error: {exc}")
