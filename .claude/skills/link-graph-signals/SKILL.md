---
name: link-graph-signals
description: >
  Analyse a site's internal link graph from a Spy crawl — internal PageRank, orphans, dead ends,
  anchor text, link equity distribution and sitemap-vs-linked gaps. Use when asked why a page has no
  visibility despite existing, how link equity flows, or what to link from where.
---

# Reading the internal link graph

Spy builds a real link graph during the crawl and runs power-iteration PageRank
over it, normalised 0-100 with the best-supported page at 100. That number is
in `internal_pagerank` on every page.

## What the graph tells you that depth doesn't

Click depth says how far a page is from the homepage. PageRank says how much
the rest of the site actually vouches for it. They diverge often, and PageRank
is the better signal:

- A page at depth 1 linked only from the footer has low PageRank despite being
  "one click away".
- A page at depth 3 linked from every service page has high PageRank.

Depth is also sensitive to how the crawl was seeded — when sitemap URLs are
used as seeds, everything in the sitemap reads as depth 0-1 regardless of how
the site actually links it. **When depth looks suspiciously flat, trust
PageRank and the sitemap-vs-linked comparison instead.**

## The findings that matter

| Rule | Means |
| --- | --- |
| `SEO_LINK_016` | In the sitemap, but internal linking barely supports it |
| `SEO_LINK_003` | Dead-end pages — no outbound internal links at all |
| `SEO_LINK_004` | Broken external links (only 404/410 count) |
| `SEO_LINK_005` | Redirect loops — a hard dead end |

`SEO_LINK_016` is usually the most actionable thing in this whole dimension: it
names pages the site itself declared important enough to publish in a sitemap,
while linking to them from almost nowhere. The fix is nearly always a
related-content block or a nav entry on a template, which fixes every affected
page at once.

## Reading equity distribution

Use `ctx`-equivalent data from `/audits/<id>/pages`: sort by
`internal_pagerank` and look at the shape.

- **A long flat tail near zero** means a section of the site is effectively
  invisible to link equity — commonly translations, tag pages, or an archive.
- **Everything clustered near 100** means a small site with dense linking,
  which is healthy.
- **The homepage not at or near the top** is worth investigating.

Cross-reference the bottom of that list against `from_sitemap`. Pages that are
in the sitemap *and* at the bottom of PageRank are the gap; pages low in both
are usually meant to be minor.

## Anchor text

Generic anchors ("click here", "read more") waste the strongest on-page signal
about what the target page is. Worth reporting when widespread, but it is a
lower-leverage fix than getting links to unlinked pages in the first place —
order accordingly.
