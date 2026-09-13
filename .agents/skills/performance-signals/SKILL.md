---
name: performance-signals
description: >
  Interpret Spy's performance data — server response times, HTML weight, text-to-HTML ratio and
  layout-shift risk — and be precise about what it does and does not measure. Use when analysing
  the performance score or any speed-related finding.
---

# Reading Spy's performance data

## What Spy measures

`response_ms` on each page is **server response time**: how long the origin
took to return the document. Nothing else.

Plus two weight signals: `html_size` (raw bytes of the document) and the
text-to-HTML ratio derived from it.

## What Spy does not measure

Core Web Vitals. There is no LCP, no CLS, no INP, no TTFB breakdown, no
render timing, no JavaScript execution cost, no waterfall.

**This matters more than anything else in this dimension.** A `performance`
score of 100 means the server answers quickly. It says nothing about how fast
the page becomes usable, and a site can score 100 here while feeling slow to
every visitor — heavy client-side JavaScript, render-blocking resources, huge
images and web fonts are all invisible to this measurement.

Say that explicitly whenever reporting a high performance score. Letting a
perfect number imply "the site is fast" is the most misleading thing available
in a Spy audit, because it sounds like the strongest possible result.

For real field data, point the site owner at PageSpeed Insights, the Chrome UX
Report, or Search Console's Core Web Vitals report — and say so rather than
implying Spy covers it.

## The one exception: layout shift

Spy can see one genuine Core Web Vitals risk without measuring it:
`images_missing_dimensions`. An image without `width`/`height` (or a CSS
`aspect-ratio`) causes the browser to reflow when it loads, which is a direct
CLS penalty. That finding is real and worth reporting as a Core Web Vitals
issue — it is the only one here that is.

## Reading the numbers

Report percentiles rather than an average: median and p90 tell a story a mean
hides. Compute them over HTML documents only — if any non-document URLs were
crawled they will dominate the tail and make a fast site look slow.

Weight findings worth reporting:

- **Large HTML** (`SEO_CRAWL_009`) — over the configured threshold, usually
  inlined markup, embedded data or framework payload. Real but rarely urgent.
- **Low text-to-HTML ratio** (`SEO_CONTENT_005`) — common on media-heavy and
  framework-rendered sites. Worth trimming; not a defect on its own.

Neither is a reason to alarm a site owner whose server responds in 70ms.
