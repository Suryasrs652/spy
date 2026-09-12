---
name: competitor-signals
description: >
  Benchmark a site against a competitor through Spy — adding a competitor, triggering its crawl,
  reading the score comparison and the content gap. Use when asked how a site compares to a rival,
  what competitors do better, or what topics they cover that this site doesn't.
---

# Competitor benchmarking

Spy crawls a competitor's site with the same rule engine and scoring pipeline
as a real audit, just shallower, and compares the scores.

## Endpoints

All scoped to a project. `BASE` is `http://localhost:3000/api/proxy`.

| Endpoint | Does |
| --- | --- |
| `GET $BASE/projects/<pid>/competitors` | List competitors and their status |
| `POST $BASE/projects/<pid>/competitors` | Add one — `{"name": "...", "url": "https://..."}` |
| `POST $BASE/projects/<pid>/competitors/<cid>/refresh` | Re-crawl (async) |
| `GET $BASE/projects/<pid>/competitors/<cid>/compare` | Score-by-score comparison |
| `GET $BASE/projects/<pid>/competitors/<cid>/content-gap` | Terms they cover that you don't |
| `DELETE $BASE/projects/<pid>/competitors/<cid>` | Remove |

A competitor has a `status`: `PENDING` → `CRAWLING` → `COMPLETED` or `FAILED`.
Poll the list endpoint; the comparison is meaningless until `COMPLETED`.

Competitor crawls go through the same SSRF guard as everything else, so a URL
that fails validation is refused — correct behaviour, not a bug.

## Reading the comparison

`/compare` returns `comparisons`: a list of `{field, your_score,
competitor_score, delta}` plus `your_latest_audit_id`. A `null` on either side
means that dimension was not measured for that site — not a zero, and not a
win. Say "not measured".

The comparison is only as good as the two crawls behind it. The competitor
crawl is **deliberately lighter** than a full audit, so:

- Treat large deltas as directional, not precise.
- A competitor scoring lower on `authority` almost always means Spy has no
  backlink data for either site, not that they have fewer links.
- Content and schema comparisons are the most trustworthy, because they come
  from markup that was actually fetched.

## Reading the content gap

`/content-gap` returns `has_data`, `reason`, `your_terms`,
`competitor_terms`, `gap_terms` and a `methodology` string. When `has_data` is
false, the `reason` explains why — pass it through rather than reporting an
empty gap as "no gaps found".

`gap_terms` are terms prominent in their content and absent from yours. They
are a starting point for topic research, **not keywords** — there is no search
volume or difficulty behind them, and presenting them as keyword opportunities
overstates what the data supports.

## Framing the output

The useful question is not "who scores higher" — it is "what do they do that
we don't, and is it worth copying". A competitor winning on schema coverage is
actionable. A competitor winning by 3 points on a composite score is noise.
