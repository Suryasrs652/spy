---
name: contradiction-resolution
description: >
  Resolve disagreements between analysis agents before they reach a report — where two agents
  describe the same evidence differently, where a score contradicts the per-page data behind it, or
  where one agent's fix would undo another's. Use after validation, when several analyses must be
  merged into one account.
---

# Resolving contradictions between analyses

Several agents read overlapping evidence from different angles. When they
disagree, one of them is wrong, they mean different things by the same word, or
the underlying data is itself inconsistent. Each needs a different response,
and merging the findings without deciding which produces a report that argues
with itself.

## The four kinds, and what to do

**1. An aggregate contradicts its own per-page data.**
The most consequential kind, because it usually means the metric is measuring
something other than its name. A real example from this scanner: the heading
hygiene input (now part of GEO's `ai_readable_structure`) reported 100% while
12 of 70 pages had `heading_order_valid: false`. The aggregate was counting
H1s, not heading order.

*Resolution:* the per-page evidence wins — it is closer to the source. Report
the per-page figure, flag the aggregate as suspect, and name the field.

**2. Two agents describe the same evidence differently.**
Usually a vocabulary mismatch rather than a factual one. One agent calls pages
"buried at depth 4"; another says they are "in the sitemap but weakly linked".
Both read the same pages.

*Resolution:* find the claim they actually share, state it once in the terms
that survive scrutiny, and drop the framing that depends on a measurement
artifact. Do not present both.

**3. Two findings imply conflicting fixes.**
One agent wants a page consolidated; another wants it expanded. One wants
`noindex`; another wants more internal links to it.

*Resolution:* this is a genuine decision, not an error. Surface it explicitly
with the tradeoff, and recommend one — with the reason. Never silently pick a
side, and never emit both instructions as if they were compatible.

**4. A finding contradicts the live site.**
The validator should have caught it, but a contradiction between two agents is
sometimes how it first shows.

*Resolution:* check the site yourself. The live response wins over any stored
evidence or any agent's reading of it.

## How to decide

Rank sources of truth, highest first:

1. The live site, fetched now.
2. Per-page stored evidence (`/audits/<id>/pages`).
3. Aggregated scores and percentages.
4. An agent's interpretation of any of the above.

A lower rank never overturns a higher one. Most contradictions dissolve as
soon as they are placed on this ladder.

## What to hand on

For each contradiction: what disagreed, which source you trusted and why, and
the single resolved statement that should appear in the report.

Where the contradiction revealed a defect in the tool rather than the site —
a mislabelled metric, an aggregate that doesn't match its inputs — say so
separately. That is a finding about the scanner, and it belongs in the report's
own account of its reliability rather than being quietly smoothed away.

Resolving is not averaging. Two incompatible claims do not become one true
claim by being softened; one of them is wrong and the reader needs to know
which.
