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
from urllib.parse import urlsplit

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
MAX_SCHEMA_BLOCKS_STORED = 10  # cap per page — enough for field-level checks without bloating the row
MAX_EXTERNAL_LINKS_CHECKED = 25  # sampled, not exhaustive — bounds worst-case audit time

# Media and binary assets get linked like pages but aren't documents: they
# have no title, headings, schema or outbound links to contribute, and
# fetching them means pulling whole video files through the crawler (a
# single .mp4 took 1.9s on one real audit). They still appear in the link
# graph — they're just never enqueued as pages to fetch and score.
NON_DOCUMENT_EXTENSIONS = frozenset({
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".mpg", ".mpeg",
    ".mp3", ".wav", ".ogg", ".oga", ".m4a", ".flac", ".aac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp", ".tiff",
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".dmg", ".exe", ".msi", ".apk",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".css", ".js", ".mjs", ".map", ".json", ".xml", ".rss", ".atom",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
})


def _is_document_url(url: str) -> bool:
    """Extension-based, so it only ever skips URLs whose type is
    unambiguous from the path — anything extensionless or dynamic still
    gets fetched and decided on its real Content-Type.
    """
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    if dot == -1 or "/" in path[dot:]:
        return True
    return path[dot:] not in NON_DOCUMENT_EXTENSIONS

SECURITY_HEADER_NAMES = (
    "strict-transport-security", "x-content-type-options", "content-security-policy",
    "x-frame-options", "referrer-policy", "server", "set-cookie", "permissions-policy",
)


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
    # Site-wide facts the rule engine can't derive from a single page (§144
    # M2 rule expansion) — fed to run_all_rules as `site_facts`.
    robots_txt_found: bool = False
    robots_disallow_all: bool = False
    sitemap_found: bool = False
    max_urls_reached: bool = False


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
    pending_links: list[tuple[str, str, object]] = []  # (source_url, target_url, ExtractedLink)

    try:
        policy = await fetch_robots_policy(fetcher, origin=origin, user_agent=settings.crawler_user_agent)
        result.robots_txt_found = policy.found
        result.robots_disallow_all = policy.disallows_everything(origin, settings.crawler_user_agent)

        sitemap_url_set: set[str] = set()
        try:
            sitemap_urls = await discover_sitemap_urls(
                fetcher, origin=origin, robots_sitemaps=policy.sitemap_urls, max_urls=max_urls
            )
            for u in sitemap_urls:
                try:
                    sitemap_url_set.add(normalize_url(u))
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001 - sitemap discovery is best-effort
            logger.warning("sitemap_discovery_failed", audit_id=str(audit_id))
        result.sitemap_found = len(sitemap_url_set) > 0

        seed_urls: list[str] = [origin + "/", *sitemap_url_set]

        frontier: list[tuple[str, int]] = []
        seen_frontier: set[str] = set()
        for u in seed_urls:
            try:
                n = normalize_url(u)
            except Exception:  # noqa: BLE001
                continue
            if n not in seen_frontier and _is_document_url(n):
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

            for (url, depth), outcome in zip(batch, fetch_results, strict=False):
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
                page.from_sitemap = url in sitemap_url_set
                result.pages.append(page)
                page_id_by_url[url] = page.id
                result.urls_processed += 1

                if parsed is not None:
                    for link in links:
                        pending_links.append((url, link.target_url, link))
                        if (
                            link.is_internal
                            and _is_document_url(link.target_url)
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

        result.max_urls_reached = len(visited) >= max_urls

        status_by_url = {p.url: p.status_code for p in result.pages}

        # §23 Links "broken links" — sample a bounded set of *external*
        # targets and actually check them (internal targets are already
        # known from the crawl itself). Bounded so one audit can't balloon
        # into checking thousands of external URLs.
        external_targets = {t for _s, t, link in pending_links if not link.is_internal}
        external_status = await _check_external_links(fetcher, external_targets)

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
                    # Known when the target was crawled internally this run,
                    # or was one of the sampled external checks; otherwise
                    # stays None (undetermined) rather than a stale guess.
                    status_code=status_by_url.get(target_url) or external_status.get(target_url),
                )
            )

        return result
    finally:
        await fetcher.aclose()


async def _check_external_links(fetcher: SafeFetcher, targets: set[str]) -> dict[str, int]:
    """Best-effort status check for a bounded sample of external link
    targets (§23 "broken links" isn't only about internal ones). Every
    fetch still goes through the same SSRF-guarded `SafeFetcher` — an
    external link that itself resolves to a private address is correctly
    rejected, not silently skipped.
    """
    sample = list(targets)[:MAX_EXTERNAL_LINKS_CHECKED]
    if not sample:
        return {}

    async def _check_one(url: str) -> tuple[str, int | None]:
        try:
            result = await asyncio.wait_for(fetcher.fetch(url), timeout=8.0)
            return url, result.response.status_code
        except Exception:  # noqa: BLE001 - unreachable/blocked/timed-out external link => undetermined
            return url, None

    outcomes = await asyncio.gather(*[_check_one(u) for u in sample])
    return {url: status for url, status in outcomes if status is not None}


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

    chain = [*fetch_result.redirect_chain, fetch_result.final_url]
    is_loop = len(set(chain)) < len(chain)

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
        redirect_count=len(fetch_result.redirect_chain),
        is_redirect_loop=is_loop,
        x_robots_tag=response.headers.get("x-robots-tag"),
        security_headers=_extract_security_headers(response.headers),
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
    page.h2_count = parsed.h2_count
    page.h3_count = parsed.h3_count
    page.heading_order_valid = parsed.heading_order_valid
    page.canonical_url = parsed.canonical_url
    page.robots_meta = parsed.robots_meta
    page.word_count = parsed.word_count
    page.content_hash = parsed.content_hash
    page.html_hash = parsed.html_hash
    page.images_total = parsed.images_total
    page.images_missing_alt = parsed.images_missing_alt
    page.images_missing_dimensions = parsed.images_missing_dimensions
    page.images_generic_alt = parsed.images_generic_alt
    page.has_schema = len(parsed.schema_blocks) > 0
    page.schema_types = _extract_schema_types(parsed.schema_blocks)
    page.schema_blocks = parsed.schema_blocks[:MAX_SCHEMA_BLOCKS_STORED]
    page.schema_invalid = len(parsed.schema_errors) > 0
    page.mixed_content = parsed.mixed_content
    page.has_og_title = parsed.has_og_title
    page.has_og_description = parsed.has_og_description
    page.has_og_image = parsed.has_og_image
    page.has_twitter_card = parsed.has_twitter_card
    page.has_viewport_meta = parsed.has_viewport_meta
    page.has_charset_meta = parsed.has_charset_meta
    page.has_favicon = parsed.has_favicon
    page.html_lang = parsed.html_lang
    page.hreflang_tags = [{"lang": t.lang, "url": t.url} for t in parsed.hreflang_tags]
    page.has_insecure_form_action = parsed.has_insecure_form_action
    page.word_frequency_top_ratio = parsed.word_frequency_top_ratio
    page.question_heading_count = parsed.question_heading_count
    page.list_count = parsed.list_count
    page.table_count = parsed.table_count
    page.has_definition_list = parsed.has_definition_list
    page.has_author_byline = parsed.has_author_byline

    robots_meta_lower = (parsed.robots_meta or "").lower()
    x_robots_lower = (page.x_robots_tag or "").lower()
    page.indexable = (
        "noindex" not in robots_meta_lower
        and "noindex" not in x_robots_lower
        and response.status_code < 400
    )

    return page, parsed, parsed.links


def _extract_security_headers(headers) -> dict:
    return {name: headers[name] for name in SECURITY_HEADER_NAMES if name in headers}


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
