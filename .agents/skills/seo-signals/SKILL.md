---
name: seo-signals
description: >
  Interpret Spy's classic SEO findings — metadata, indexability, headings, content quality, images,
  internal links, security headers, crawlability and hreflang. Use when analysing the seo_score,
  reading the issues list, deciding which SEO problems actually matter for a site, or explaining what
  a SEO_* rule id means and what it costs.
---

# Reading Spy's SEO output

`seo_score` is one of the three headline scores (with AEO and GEO), and it is
itself seven components out of 100:

| Component | Weight | Built from |
| --- | --- | --- |
| `technical` | 25 | `SEO_CRAWL_*`, `SEO_INDEX_*`, `SEO_SEC_*`, `SEO_INTL_*` |
| `onpage` | 20 | `SEO_META_*`, `SEO_IMG_*` |
| `content` | 20 | `SEO_CONTENT_*` |
| `internal_links` | 10 | `SEO_LINK_*` |
| `structured_data` | 10 | `SEO_SCHEMA_*` |
| `performance` | 10 | Measured response times |
| `authority` | 5 | Referring domains + internal PageRank |

Each is 100 minus a deduction per finding, scaled by severity and by how much
of the site the finding affects. Read `evidence.seo.components` for the
numbers and `evidence.seo.weights_used` for the weights actually applied —
`authority` drops out whenever Spy's backlink index has nothing for the site,
and the other six are rescaled to sum to 1.

Before spy-score-v2.0 this column held the on-page score alone. Audits stamped
`spy-score-v1.0` still do, which is why comparing across versions is refused
rather than silently performed.

## Rule id map

Ids are stable and grep-able in `services/api/app/modules/seo/rules/`.

| Prefix | Covers | File |
| --- | --- | --- |
| `SEO_META_*` | Titles, descriptions, H1s, Open Graph, Twitter cards, charset | `metadata.py` |
| `SEO_CONTENT_*` | Thin/duplicate content, heading order, keyword stuffing, text ratio, depth | `content.py` |
| `SEO_LINK_*` | Dead ends, broken links, redirect chains and loops, anchor text, PageRank support | `links.py` |
| `SEO_IMG_*` | Alt text, dimensions, oversized files | `images.py` |
| `SEO_INDEX_*` | noindex, canonicals, robots meta, X-Robots-Tag | `indexability.py` |
| `SEO_SCHEMA_*` | Structured data presence and validity | `structured_data.py` |
| `SEO_INTL_*` | hreflang self-reference, reciprocity, lang agreement | `international.py` |
| `SEO_CRAWL_*` | robots.txt, sitemaps, response time, HTML weight | `crawlability.py` |
| `SEO_SEC_*` | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer/Permissions-Policy | `security.py` |

## What actually moves the needle

Severity is not priority. A rule's `severity` describes how bad one instance
is; what matters to a site owner is severity × page count ÷ effort. The
`/recommendations` endpoint already computes that ordering — prefer it over
re-deriving your own from the raw issues list.

Two patterns come up constantly and are worth calling out by name:

**Sitewide one-line fixes.** Missing security headers fire on every page and
look alarming in the issue count, but they are a handful of lines in the host
config. High count, trivial effort, and they hold the `technical` sub-score
down — usually the single best first move.

**High-count content work.** Missing alt text or heading-order breaks across
70 pages is real, but it is content labour. Say so honestly rather than
implying it is quick.

## Findings that are usually less severe than they look

- **Duplicate title / duplicate content on `/` and `/index.html`.** Check for a
  canonical first. If both canonicalise to one URL, the consolidation signal is
  already correct and this is cosmetic, not a ranking risk.
- **Title/description length.** Measured by display width, which is correct for
  Latin and approximates rendered width elsewhere — it is still not pixels.
  Treat borderline cases as advisory.
- **Low text-to-HTML ratio, large HTML.** Common on media-heavy and
  framework-rendered sites. Worth trimming, rarely urgent.

## Findings worth escalating

- **Redirect loops** (`SEO_LINK_005`) — a hard dead end for crawlers.
- **noindex or robots blocks on pages that should rank** — the page cannot win;
  nothing else about it matters until that is fixed.
- **Broken internal links** — unlike external ones, these are entirely within
  the owner's control and always worth fixing.
- **Duplicate titles across genuinely different pages** — real cannibalisation,
  distinct from the `/index.html` case above.

## Before you report

Security-header findings are verifiable in one request — `curl -sI <url>` — and
so are canonicals and meta tags. Check the specific claim before repeating it.
Findings about structured data, external links, sitemaps and hreflang have a
history of being wrong here; the `finding-validation` skill lists them.
