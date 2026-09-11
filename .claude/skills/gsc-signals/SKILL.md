---
name: gsc-signals
description: >
  Pull and interpret Google Search Console data through Spy — performance summary, top queries and
  pages, and the opportunity engine (striking distance, low CTR, zero-click, rising/declining,
  position movement, cannibalisation). Use when analysing real search performance, connecting a GSC
  property, or explaining what a site actually ranks for.
---

# Reading Spy's Search Console data

This is the only part of Spy fed by observed search behaviour rather than by
crawling. Everything here is real impressions and clicks, or it is absent.

## Connecting a property

GSC is optional and often not configured. Check first:

```bash
curl -s "$BASE/gsc/properties"
```

An empty list means no OAuth connection exists — `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` are unset, or nobody has completed the consent flow at
`/settings`. Report that as "not connected" and stop; do not substitute crawl
data for search data.

A property must also be linked to the project: match on `project_id` and
`selected`. A property with `project_id: null` is connected but unlinked.

## Endpoints

| Endpoint | Returns |
| --- | --- |
| `GET $BASE/gsc/performance?property_id=<id>&days=28` | `clicks`, `impressions`, `ctr`, `average_position`, `period` |
| `GET $BASE/gsc/queries?property_id=<id>&days=28` | Top queries with clicks/impressions/ctr/position |
| `GET $BASE/gsc/pages?property_id=<id>&days=28` | Same shape, keyed by page |
| `GET $BASE/gsc/opportunities?property_id=<id>` | The analysis below |
| `POST $BASE/gsc/sync` | Pull fresh data for selected properties |

## The opportunity engine

`/gsc/opportunities` compares the current 28-day window against the previous
one and returns:

| Key | What it is | Why it matters |
| --- | --- | --- |
| `striking_distance_keywords` | Positions ~4-20 with real impressions | Closest to page-one wins; usually the best content ROI |
| `low_ctr_opportunities` | CTR well below expected for that position | A title/description problem, not a ranking problem |
| `high_impressions_no_clicks` | Seen often, never clicked | Intent mismatch — the page isn't what searchers wanted |
| `rising_keywords` / `declining_keywords` | Click deltas vs previous period | Momentum, and early warning |
| `rising_pages` / `declining_pages` | Same, per page | |
| `position_gains` / `position_losses` | Average-position movement | |
| `keyword_cannibalization` | One query, several competing pages | Consolidate or differentiate |

**`pct_change` is a fraction, not a percentage.** `11.0` means +1100%. Multiply
by 100 before showing it to anyone — this has been rendered wrong before.

`ctr` is likewise a fraction: `0.052` is 5.2%.

## Interpreting honestly

**Low CTR at a good position is a copy problem.** Ranking #2 with 0.2% CTR
means the result is being seen and skipped — rewrite the title and description
before touching the content.

**Striking distance beats net-new content** almost always. A keyword at
position 7 with impressions already has demonstrated relevance; moving it to 3
is cheaper than ranking a new page from nothing.

**Declining clicks with stable position** usually means the SERP changed around
the site — an AI overview, more ads, a new competitor — not that the page got
worse. Say that rather than implying the page degraded.

**No data is a finding.** A site with a connected property and almost no
impressions has a discovery problem that no on-page fix addresses. Report the
absence plainly instead of filling the section with crawl-derived guesses.

Rank Tracker and the Keywords view read the same synced data, so a keyword with
no GSC impressions reports "no data" rather than a fabricated position. Preserve
that distinction.
