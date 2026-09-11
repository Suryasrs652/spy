---
name: crawl-signals
description: >
  Interpret Spy's crawl output — page inventory, status codes, indexability, click depth, internal
  PageRank, response times, sitemap coverage and redirect behaviour. Use when analysing site
  architecture, diagnosing why pages weren't found or crawled, reading /audits/<id>/pages, or
  investigating a FAILED audit.
---

# Reading Spy's crawl output

`/audits/<id>/pages` is the per-page inventory and the most factual thing the
tool produces — everything else is derived from it.

## Fields that carry the most signal

| Field | Read it for |
| --- | --- |
| `status_code` | Anything not 200 is a discovery or delivery problem |
| `indexable` | False means it cannot rank regardless of quality |
| `crawl_depth` | Clicks from the homepage — 0 is the homepage |
| `internal_pagerank` | 0-100, normalised so the best-supported page is 100 |
| `from_sitemap` | Whether the sitemap declared this URL |
| `response_ms` | Server response only, not full page load |
| `redirect_count` | Hops taken to reach the final URL |
| `robots_allowed` | Whether robots.txt permitted the fetch |
| `word_count`, `html_size` | Content volume against markup weight |

## Click depth is the architecture story

Depth is where most real structural problems show up. A healthy small site puts
nearly everything at depth 0-2. Pages at depth 4+ are reachable but weakly
supported: they inherit little internal PageRank and get crawled less often.

The pattern to watch for is a **whole section buried at one depth** — every
translated page, or an entire blog, sitting at depth 4 while the English or
top-level equivalents sit at depth 1. That is not a content problem; it means
one navigational link is missing. It is usually a template change and one of
the highest-leverage fixes available, because the pages already exist and
already have content.

Cross-reference `internal_pagerank` with `from_sitemap`: pages the sitemap
declares but internal linking barely supports are exactly the gap.

## Sitemap coverage

`from_sitemap: false` across the board means either the site has no sitemap or
the crawler failed to ingest it. Check `robots.txt` for a `Sitemap:` line and
fetch it directly before concluding the site lacks one — the sitemap may be a
`<sitemapindex>` pointing at per-language or per-section children.

Comparing sitemap URL count against crawled HTML pages tells you whether
internal linking alone can find everything. Equal counts mean the link graph is
complete, which is a genuine strength worth reporting.

## Indexability

Non-indexable pages are normal in moderation — tag pages, paginated archives,
utility pages. What matters is *which* pages: a service or product page that is
non-indexable is a bug, and worth surfacing loudly regardless of how small the
count is.

## Response times

`response_ms` is server response, not Core Web Vitals. Spy does not measure
LCP, CLS or INP, and a perfect `performance` sub-score does not mean the site
feels fast to a user. Say so rather than letting the number imply more than it
measures. Layout-shift risk does show up indirectly via images missing
dimensions.

## When an audit fails

`/audits/<id>/progress` carries `error_code`:

- `DNS_FAILURE`, `UNREACHABLE`, `SSL_ERROR` — the target site, not the tool.
- `ROBOTS_BLOCKED` — robots.txt refused the crawler. Correct behaviour.
- `BLOCKED_TARGET` — the SSRF guard rejected the URL or a redirect hop into a
  private range. Also correct behaviour; do not work around it.
- `WORKER_ERROR` — the tool. Check `docker compose logs worker --tail 50`.
  A stale worker holding old code after an edit is the usual cause.

`urls_discovered` versus `urls_processed` shows whether the crawl was capped
before finishing.
