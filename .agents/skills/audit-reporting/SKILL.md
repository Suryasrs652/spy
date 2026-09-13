---
name: audit-reporting
description: >
  Turn validated audit findings into a report someone can act on — structure, how to rank fixes by
  leverage, how to phrase what wasn't measured, and what never to claim. Use when writing the final
  deliverable from one or more analyses, or when asked for a growth strategy off audit data.
---

# Writing the audit report

The reader is usually the person who owns the site. They want to know what to
do on Monday, in what order, and what it will cost them. They do not want a
transcription of the issues list — they can read that themselves.

## Structure

1. **The headline.** Score, and the single most consequential thing found. If
   the numbers changed because a scanner defect was corrected, say so here —
   it is the difference between a report and a wrong report.
2. **What is already right.** Genuinely, with specifics. A site doing schema
   well should hear it: it is true, and it tells them what not to break.
3. **What is actually wrong**, ordered by leverage, each with the evidence
   (how many pages, what was verified) and a concrete fix.
4. **What could not be measured**, and why.
5. **Strategy**, sequenced — see below.

## Rank by leverage, not severity

Severity says how bad one instance is. Leverage is impact × reach ÷ effort, and
it is what determines what to do first. A `LOW` finding on 89 pages that is
twelve lines of host config outranks a `HIGH` on two pages needing a rewrite.
`/audits/<id>/summary` and `/audits/<id>/recommendations` already compute
this, and they answer different questions — use both rather than picking one:

- **`summary.blockers`** is ordered by *magnitude*: how many points of the
  Overall Digital Search Score each thing is costing right now. Crucially it
  draws on the AEO and GEO score components as well as the rule findings,
  which matters because no rule fires on "no page carries a byline" or "10% of
  pages state a checkable figure" — those weaknesses exist only in the scores
  and otherwise never reach a list of things to do. A blocker with
  `source: SIGNAL` is one of those.
- **`recommendations`** is ordered by *leverage* — `impact × confidence ×
  reach ÷ effort` — so it starts with the cheapest useful fix.

Lead with the blockers (what is actually holding the site down), then use the
recommendations for sequencing (what to do on Monday). Saying which list is
which matters: a reader who thinks they are the same list will wonder why the
orders disagree.

`summary.issue_counts` gives both `issues` and `pages` per severity. Quote
both — one issue across seventy pages and seventy issues on one page each look
identical with only one of them, and they are not the same site.

Group by when, not by category: this week / this month / this quarter. Put the
effort next to each item. "Write 75 alt attributes" is honest; "add alt text"
hides two hours.

## Name the binding constraint

Most sites do not need a list of everything wrong. They need to know the one or
two things holding them back. A technically flawless site with no inbound links
and no bylines has an **authority and attribution** problem — listing twenty
`LOW` findings above that actively buries the answer.

Say plainly when further on-page work has a low ceiling. That is more useful
than another twenty recommendations.

## Language that stays honest

| Don't write | Write |
| --- | --- |
| "Authority score: 0" | "Authority: not measured — no backlink data" |
| "This will rank you #1" | "This removes a constraint on ranking" |
| "You'll appear in ChatGPT" | "This makes the site a stronger citation candidate" |
| "Some images lack alt text" | "75 images across 70 pages" |
| "Fix your schema" | "Add `Organization` markup to the homepage with logo and sameAs" |

Never present an estimate as a measurement. If Spy did not produce a number, do
not supply one — traffic projections, keyword volumes and difficulty scores are
not available here and inventing them is the fastest way to make the whole
report untrustworthy.

## Growth strategy

Sequence by what unblocks what, not by severity:

- **Mechanical first** — the config-level fixes that move scores immediately
  and cost an hour.
- **Then content and structure** — authorship, question coverage, internal
  linking. Weeks, and they compound.
- **Then the actual constraint** — usually authority, which is off-site and
  slow, and which no amount of on-page work substitutes for.

If the site has zero measurable backlinks, say that this is the binding
constraint and that the first ten relevant referring domains will move things
further than another hundred hours of on-page work. That is the honest read.

## Publishing

A finished report with an audience belongs in a form they can keep and share,
not buried in terminal output. Publish it as an artifact and hand over the
link. Keep the prose tight — density beats length, and a report nobody finishes
helps nobody.
